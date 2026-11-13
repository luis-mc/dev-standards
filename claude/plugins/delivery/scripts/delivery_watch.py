#!/usr/bin/env python3
"""Delivery watcher: a background loop with no model that acts on time-critical steps.

DELIVERYSPEC section 4(a) and owner decisions D5, D6. Each pass, against .delivery/ledger.json:

  agents    git ls-remote of the agent's branch, an injectable routine-status fetcher and the
            log file's mtime give head_sha, last_activity and state; an agent whose branch has
            been idle for more than twice its work estimate is `stalled`.
  trains    CI is read for the PR's CURRENT head (`gh pr view` then `gh run list --commit SHA
            --workflow ci.yml`), never from the PR's check list. When it is green and the train
            has no hold: `gh pr merge N --merge` (never --auto), then the next joined train is
            pushed and its ready PR opened. CI runs of the same branch for an older head are
            cancelled (`gh run cancel`).
  CI runs   while a train's CI runs, runs of other (non-train) branches, such as dependabot/*,
            are cancelled and recorded in held_runs; when no train's CI runs, they are re-run
            (`gh run rerun`).
  installs  configured update-state files (install_state_files: [{product, path}]).
  runners   `gh api repos/{owner}/{repo}/actions/runners`.
  watchers  a heartbeat row.
  runners   the CI runner guard (D6a): `runner_plan.py runners` is launched by this loop, once, and
            relaunched when it exits, so the project does not have to start it.

.delivery/config.json decides what is allowed (delivery_config.py): `watcher.push_trains`,
`watcher.open_prs`, `watcher.merge_on_green`, `watcher.manage_runners`, `runner_plan.cancel_replaced_runs`,
`runner_plan.hold_dependabot_during_train`. All default to true, which is the 0.1.0 behaviour. A merge
runs only when the PR head is still the commit whose CI was green: `gh pr merge N --merge
--match-head-commit SHA`, never --auto.

Every gh and git call goes through one injectable Shell, so tests mock them. --once runs a single
pass; --dry-run prints the actions and performs none. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import delivery_ledger as L  # noqa: E402
import delivery_config as C  # noqa: E402
import ci_runs as CR  # noqa: E402

DEFAULT_INTERVAL = 60
DEFAULT_CHECK_MIN = 15
WORKFLOW = "ci.yml"
ACTIVE_CI_STATES = ("pushed", "ci")
CI_RUNS_MIN_INTERVAL_S = 60
RUN_FIELDS = "databaseId,status,conclusion,headSha,headBranch,event,workflowName,startedAt,updatedAt,createdAt"


# DL109: on Windows a console child of a process with no visible console opens its own window; every gh and git
# call the watcher makes would flash one. CREATE_NO_WINDOW keeps them hidden.
NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


class Shell:
    """The one seam for gh and git. run(argv, cwd) -> (returncode, stdout, stderr)."""

    def run(self, argv: list[str], cwd=None, timeout: int = 120):
        try:
            p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, **NO_WINDOW)
            return p.returncode, p.stdout, p.stderr
        except (OSError, subprocess.SubprocessError) as exc:
            return 127, "", str(exc)

    def spawn(self, argv: list[str], cwd=None):
        """Start a long-running child without waiting; None when it cannot start."""
        try:
            return subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, **NO_WINDOW)
        except OSError:
            return None


OK_CONCLUSIONS = ("success", "skipped")      # a skipped run counts as success (DL-03)
_ON_PR_RE = re.compile(r"\bpull_request(?:_target)?\b")


_PR_HEAD_TYPES = ("opened", "synchronize", "reopened")


def _runs_on_every_pr_commit(block: list) -> bool:
    """True when the `on:` block (its lines) starts the workflow for every commit pushed to a pull request: a
    pull_request trigger with no paths filter and, when types are given, opened, synchronize or reopened among them.
    A closed-only trigger (cleanup) or a paths filter (runs only when some files change) never has a run to wait for
    on most heads, so such a workflow is not required (DL-03)."""
    text = "\n".join(block)
    if not _ON_PR_RE.search(text):
        return False
    pr_at = None
    for i, ln in enumerate(block):
        if re.match(r"^\s*pull_request(?:_target)?\s*:", ln):
            pr_at = i
            break
    if pr_at is None:                     # inline form: `on: [push, pull_request]` or `on: pull_request`
        return True
    indent = len(block[pr_at]) - len(block[pr_at].lstrip())
    sub = []
    for ln in block[pr_at + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
            break
        sub.append(ln)
    body = "\n".join(sub)
    if re.search(r"^\s*paths(?:-ignore)?\s*:", body, re.M):
        return False
    m = re.search(r"^\s*types\s*:\s*(.*)$", body, re.M)
    if m:
        kinds = set(re.findall(r"[a-z_]+", m.group(1)))
        if not kinds:                     # a block list on the next lines
            kinds = set(re.findall(r"^\s*-\s*([a-z_]+)", body[m.end():], re.M))
        return bool(kinds & set(_PR_HEAD_TYPES))
    return True


def pr_workflows(root) -> list:
    """The workflow files under .github/workflows that run on every pull-request commit (DL-03). A workflow that
    runs only on push, only when a pull request closes, or only when some paths change is not in the list."""
    out = []
    d = Path(root) / ".github" / "workflows"
    try:
        files = sorted(p for p in d.iterdir() if p.suffix in (".yml", ".yaml"))
    except OSError:
        return out
    for p in files:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        block, inside = [], False
        for ln in lines:
            m = re.match(r"""^["']?on["']?\s*:(.*)$""", ln)
            if m:
                inside = True
                block.append(m.group(1))
            elif inside and (not ln.strip() or ln[:1] in " \t#-"):
                block.append(ln.split("#")[0])
            elif inside:
                break
        if _runs_on_every_pr_commit(block):
            out.append(p.name)
    return out


def ci_wall(runs: list, state: str) -> dict:
    """DL168: when the CI runs of one commit started and ended, for the ledger. Empty unless the state is final."""
    if state not in ("success", "failure"):
        return {}
    starts = [r.get("startedAt") or r.get("createdAt") for r in runs if isinstance(r, dict)]
    ends = [r.get("updatedAt") for r in runs if isinstance(r, dict)]
    starts = [x for x in starts if isinstance(x, str) and x]
    ends = [x for x in ends if isinstance(x, str) and x]
    if not starts or not ends:
        return {}
    return {"run_started_at": min(starts), "run_completed_at": max(ends)}


def ci_state_from_runs(runs: list[dict], required: list[str] | None = None) -> str:
    """queued (a required workflow has no run yet), running, success or failure for the runs of one commit.
    Success needs every required workflow's latest run completed with conclusion success (DL-03); a sibling
    workflow that finished first never counts for another. Runs carry `_workflow` (the file asked for)."""
    required = required or [WORKFLOW]
    latest: dict[str, dict] = {}
    for r in runs or []:
        key = r.get("_workflow") or r.get("workflowName") or WORKFLOW
        if key not in latest or (r.get("databaseId") or 0) >= (latest[key].get("databaseId") or 0):
            latest[key] = r
    mine = [latest[w] for w in required if w in latest]
    if any(r.get("status") != "completed" for r in mine):
        return "running"
    if any(r.get("conclusion") not in OK_CONCLUSIONS for r in mine):
        return "failure"
    if len(mine) < len(required):
        return "queued" if not mine else "running"
    return "success"


DOCS_SUMMARIES = ".delivery/docs-summaries.md"


class Watcher:
    def __init__(self, root, sh=None, dry_run=False, now=None, routine_fetcher=None,
                 out=print, repo=None, ci_runs=True):
        self.root = Path(root)
        self.sh = sh or Shell()
        self.dry = dry_run
        self._now = now or L.utcnow
        self.routine_fetcher = routine_fetcher or (lambda agent: None)
        self.out = out
        self.cfg = L.load_config(self.root)
        self.flags = C.watcher_flags(self.cfg)
        self.rp = C.runner_plan_flags(self.cfg)
        self.runner_child = None
        self._guard_missing_logged = False
        self._guard_start_logged = False
        self._bad_ci_logged: set = set()
        self._extras_logged: set = set()
        self._extra_required: list = []
        self._ready_cache: dict = {}
        self.repo = repo
        self.ci_runs = ci_runs
        self.repo_args = ["--repo", repo] if repo else []
        self.actions: list[list[str]] = []

    # -- seams --
    def now(self) -> datetime:
        return self._now()

    def read(self, argv: list[str]):
        return self.sh.run(argv, cwd=str(self.root))

    def act(self, argv: list[str]):
        """A write (merge, push, cancel, rerun, pr create). Dry run only prints it."""
        if argv[:3] == ["gh", "pr", "merge"] and any(a.startswith("--auto") for a in argv):
            raise AssertionError("gh pr merge --auto is never used (D5)")
        self.actions.append(argv)
        if self.dry:
            self.out("dry-run: " + " ".join(argv))
            return 0, "", ""
        return self.sh.run(argv, cwd=str(self.root))

    def gh_json(self, args: list[str]):
        rc, out, _ = self.read(["gh", *args])
        if rc != 0:
            return None
        try:
            return json.loads(out or "null")
        except ValueError:
            return None

    def mut(self, fn) -> None:
        if not self.dry:
            L.update(self.root, fn, wait=5)

    # -- agents --
    def pass_agents(self) -> None:
        led = L.load(self.root)
        now = self.now()
        self._fetched = False
        self._default = None
        for idx, a in enumerate(led["agents"]):
            if a.get("state") not in ("queued", "running", "pushed", "stalled"):
                continue
            changes: dict = {}
            activity = L.parse_iso(a.get("last_activity")) or L.parse_iso(a.get("started"))
            branch = a.get("branch")
            remote_seen = None
            if branch and a.get("where") != "cloud-skip":
                rc, out, _ = self.read(["git", "ls-remote", "origin", "refs/heads/%s" % branch])
                sha = out.split()[0] if rc == 0 and out.strip() else None
                remote_seen = bool(sha) if rc == 0 else None
                if sha and sha != a.get("head_sha"):
                    changes["head_sha"] = sha
                    activity = now
                    if a.get("state") in ("queued", "running", "stalled"):
                        changes["state"] = "pushed"
            lp = a.get("log_path")
            if lp:
                try:
                    m = datetime.fromtimestamp(os.stat(lp).st_mtime, tz=now.tzinfo)
                    if not activity or m > activity:
                        activity = m
                except OSError:
                    pass
            routine = self.routine_fetcher(a) if a.get("where") == "cloud" else None
            if isinstance(routine, dict):
                if routine.get("state") in ("done", "failed", "stopped", "running", "empty"):
                    changes["state"] = routine["state"]
                ra = L.parse_iso(routine.get("last_activity"))
                if ra and (not activity or ra > activity):
                    activity = ra
            if activity:
                changes["last_activity"] = L.iso(activity)
            state = changes.get("state", a.get("state"))
            work = ((a.get("eta") or {}).get("breakdown") or {}).get("work")
            if state in ("running", "pushed", "stalled") and work and activity:
                idle = (now - activity).total_seconds() / 60.0
                if idle > 2 * float(work):
                    changes["state"] = "stalled"
                elif state == "stalled":
                    changes["state"] = "running"
            if (changes.get("state") or a.get("state")) in ("queued", "running", "pushed", "stalled"):
                closed = self.branch_signal(a, changes.get("head_sha") or a.get("head_sha"), branch, remote_seen)
                if closed:
                    changes.update(closed)
            if changes:
                self._apply_agent(idx, a, changes)

    # -- branch signals (DL14, D20): how a finished agent row is closed without claude.ai --
    def _default_branch(self) -> str:
        if getattr(self, "_default", None) is None:
            rc, out, _ = self.read(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
            name = out.strip().split("/", 1)[1] if rc == 0 and "/" in out.strip() else "main"
            self._default = name
        return self._default

    def _fetch_once(self) -> None:
        """One fetch per tick, only when a row needs it."""
        if not getattr(self, "_fetched", False):
            self._fetched = True
            self.read(["git", "fetch", "--quiet", "origin"])

    def _report_verdict(self, a: dict, branch: str):
        """'ready', 'not-ready' or None from the last non-empty line of the branch's report file."""
        ref = "origin/%s" % branch
        paths = [a["report"]] if a.get("report") else []
        if not paths and a.get("task"):
            rc, out, _ = self.read(["git", "ls-tree", "-r", "--name-only", ref, "--", "docs/work/"])
            if rc == 0:
                paths = [x for x in out.split() if os.path.basename(x).startswith(str(a["task"])) and x.endswith(".md")]
        for path in paths:
            rc, out, _ = self.read(["git", "show", "%s:%s" % (ref, path)])
            lines = [x.strip() for x in out.splitlines() if x.strip()] if rc == 0 else []
            if lines and lines[-1].startswith("NOT READY"):
                return "not-ready"
            if lines and lines[-1].startswith("READY"):
                return "ready"
        return None

    def branch_signal(self, a: dict, head, branch, remote_seen):
        """Fields that close an open agent row, or None. Signals: merged, deleted, report-ready, report-not-ready.
        `remote_seen` is False when ls-remote failed (nothing is concluded then)."""
        if not branch or a.get("where") == "cloud-skip" or remote_seen is None:
            return None
        done = lambda by: {"state": "done", "done_by": by, "needs_check": by == "report-not-ready",
                           "done_at": L.iso(self.now()), "finished_at": L.iso(self.now())}
        if not remote_seen:                               # ls-remote answered, no such branch
            # Only a branch the ledger saw before counts as deleted. A branch that never appeared is an agent that
            # has not pushed yet (a late start is common); the session check after the ETA covers it (DL-32a).
            return done("deleted") if a.get("head_sha") else None
        self._fetch_once()
        default = self._default_branch()
        if head and a.get("head_sha"):                    # the ledger saw the branch before this tick
            rc, tip, _ = self.read(["git", "rev-parse", "origin/%s" % default])
            if rc == 0 and tip.strip() != head:
                rc, _, _ = self.read(["git", "merge-base", "--is-ancestor", head, "origin/%s" % default])
                if rc == 0:
                    return done("merged")
        verdict = self._report_verdict(a, branch)
        if not verdict:
            return None
        out = done("report-" + verdict)
        rc, when, _ = self.read(["git", "log", "-1", "--format=%cI", "origin/%s" % branch])   # DL168: the report push
        stamp = L.parse_iso(when.strip()) if rc == 0 and when.strip() else None
        out["finished_at"] = L.iso(stamp) if stamp else out["done_at"]
        return out

    def _apply_agent(self, idx: int, before: dict, changes: dict) -> None:
        def fn(led):
            row = next((x for x in led["agents"] if x.get("id") == before.get("id") and
                        x.get("branch") == before.get("branch") and x.get("task") == before.get("task")), None)
            if row is None:
                return
            if changes.get("state") and changes["state"] != row.get("state"):
                by = changes.get("done_by")
                L.add_event(led, "agent.%s" % changes["state"],
                            str(row.get("task") or row.get("id")) + (" by %s" % by if by else ""), "delivery_watch")
            row.update(changes)
        self.mut(fn)
        if self.dry:
            self.out("dry-run: agent %s -> %s" % (before.get("task"), changes))

    # -- agent checks (DS33, DL-32) --
    def check_interval_min(self) -> float:
        w = self.cfg.get("watcher") if isinstance(self.cfg.get("watcher"), dict) else {}
        try:
            return float(w.get("check_interval_min") or self.cfg.get("check_interval_min") or DEFAULT_CHECK_MIN)
        except (TypeError, ValueError):
            return float(DEFAULT_CHECK_MIN)

    def _cloud_pr(self, a: dict):
        """The agent's newest PR: by its branch, else by the task id prefix claude/<task>-*. None when unknown."""
        fields = "number,headRefName,headRefOid,isDraft,state,updatedAt,commits"
        branch = a.get("branch")
        found = None
        if branch:
            found = self.gh_json(["pr", "list", "--head", branch, "--state", "all", "--json", fields, *self.repo_args])
        if not found and a.get("task"):
            found = self.gh_json(["pr", "list", "--state", "all", "--search", "head:claude/%s-" % a["task"],
                                  "--json", fields, *self.repo_args])
        if not isinstance(found, list):
            return None
        found = [p for p in found if isinstance(p, dict)]
        return max(found, key=lambda p: p.get("number") or 0) if found else None

    def check_agent(self, a: dict) -> dict:
        """Read one running agent's real signs of life. Returns the fields to record. It never returns a
        state: only the routine fetcher in pass_agents may say an agent ended (no done by guess)."""
        now = self.now()
        ch: dict = {"last_checked": L.iso(now)}
        newest = L.parse_iso(a.get("last_activity")) or L.parse_iso(a.get("started"))
        notes = []

        def see(dt):
            nonlocal newest
            if dt and (not newest or dt > newest):
                newest = dt

        if str(a.get("id", "")).startswith("trig_") or a.get("where") == "cloud":
            pr = self._cloud_pr(a)
            if pr is None:
                notes.append("no PR yet")
            else:
                ch["head_sha"] = pr.get("headRefOid") or a.get("head_sha")
                ch["branch"] = pr.get("headRefName") or a.get("branch")
                ch["pr"] = pr.get("number")
                commits = pr.get("commits") if isinstance(pr.get("commits"), list) else []
                dates = [L.parse_iso(c.get("committedDate")) for c in commits if isinstance(c, dict)]
                see(max([d for d in dates if d], default=None))
                notes.append("PR #%s %s" % (pr.get("number"),
                                            "draft" if pr.get("isDraft") else str(pr.get("state") or "").lower()))
                if ch["head_sha"]:
                    runs = self.gh_json(["run", "list", "--commit", ch["head_sha"], "--limit", "20", "--json",
                                         "status,conclusion,workflowName,updatedAt,createdAt", *self.repo_args])
                    if isinstance(runs, list) and runs:
                        open_ = [r for r in runs if r.get("status") != "completed"]
                        bad = [r for r in runs if r.get("status") == "completed"
                               and r.get("conclusion") not in ("success", "skipped", "neutral")]
                        notes.append("runs %d, %d open, %d failed" % (len(runs), len(open_), len(bad)))
                        for r in runs:
                            see(L.parse_iso(r.get("updatedAt")) or L.parse_iso(r.get("createdAt")))
                        if open_:
                            see(now)    # CI in progress for its head is activity
        else:
            lp = a.get("log_path")
            if lp:
                try:
                    see(datetime.fromtimestamp(os.stat(lp).st_mtime, tz=now.tzinfo))
                    notes.append("log updated")
                except OSError:
                    notes.append("log missing")
            if a.get("branch"):
                rc, out, _ = self.read(["git", "ls-remote", "origin", "refs/heads/%s" % a["branch"]])
                if rc == 0 and out.strip():
                    ch["head_sha"] = out.split()[0]
                    notes.append("branch head %s" % ch["head_sha"][:7])
        if newest:
            ch["last_activity"] = L.iso(newest)
        eta = (a.get("eta") or {}).get("breakdown") or {}
        limit = float(eta.get("work") or 0) + float(eta.get("checks") or 0)
        idle = (now - newest).total_seconds() / 60.0 if newest else None
        ch["stalled"] = bool(limit and idle is not None and idle > limit)
        if ch["stalled"]:
            notes.append("STALLED: no activity for %d min (limit %d)" % (idle, limit))
        ch["check_note"] = "; ".join(notes)[:300]
        return ch

    def pass_checks(self) -> None:
        """Every check_interval_min (default 15) each `running` agent row is checked and last_checked recorded,
        independent of the session (its cron only fires when the session is idle: DL-32)."""
        led = L.load(self.root)
        now = self.now()
        every = self.check_interval_min()
        for a in led["agents"]:
            if a.get("state") != "running":
                continue
            last = L.parse_iso(a.get("last_checked"))
            if last and (now - last).total_seconds() / 60.0 < every:
                continue
            ch = self.check_agent(a)
            ident = (a.get("id"), a.get("branch"), a.get("task"))

            def fn(led2, ident=ident, ch=ch):
                row = next((x for x in led2["agents"]
                            if (x.get("id"), x.get("branch"), x.get("task")) == ident), None)
                if row is None or row.get("state") != "running":
                    return
                row.update(ch)
                L.add_event(led2, "agent.checked", "%s %s" % (row.get("task") or row.get("id"), ch.get("check_note", "")),
                            "delivery_watch")
            self.mut(fn)
            if self.dry:
                self.out("dry-run: check %s -> %s" % (a.get("task") or a.get("id"), ch))

    # -- trains --
    def current_head(self, train: dict):
        pr = train.get("pr")
        data = self.gh_json(["pr", "view", str(pr), "--json", "headRefOid,state", *self.repo_args])
        if not isinstance(data, dict):
            return None, None
        return data.get("headRefOid"), data.get("state")

    def runs_for_commit(self, sha: str, train: dict | None = None, ready_at: datetime | None = None):
        """The runs that count for one commit; None when gh failed. The configured workflows (watcher.ci_workflows)
        are listed one by one. DL298: one more listing without --workflow adds every other workflow that has a
        pull_request run on the head (a path-filtered one that never started adds nothing). Runs created before
        `ready_at` (draft-time runs) are dropped."""
        self._extra_required = []
        out = []
        needed = self.workflows_needed()
        for wf in needed:
            data = self.gh_json(["run", "list", "--commit", sha, "--workflow", wf, "--limit", "100",
                                 "--json", RUN_FIELDS, *self.repo_args])
            if not isinstance(data, list):
                return None
            out += [dict(r, _workflow=wf) for r in data
                    if isinstance(r, dict) and str(r.get("headSha", sha)).startswith(sha[:7])]
        if needed:
            everything = self.gh_json(["run", "list", "--commit", sha, "--limit", "100",
                                       "--json", RUN_FIELDS + ",workflowDatabaseId", *self.repo_args])
            if not isinstance(everything, list):
                return None
            out += self._extra_runs(sha, out, everything, train)
        if ready_at is not None:
            out = [r for r in out if not self._before(r, ready_at)]
        contexts = C.cloud_contexts(self.root, self.cfg)
        if contexts:
            statuses = self.statuses_for_commit(sha, contexts)
            if statuses is None:
                return None
            out += statuses
        return out

    @staticmethod
    def _before(run: dict, when: datetime) -> bool:
        made = L.parse_iso(run.get("createdAt"))
        return made is not None and made < when

    def _extra_runs(self, sha: str, configured: list, everything: list, train) -> list:
        """Runs of workflows that are not configured: event pull_request only, not in watcher.ignore_workflows."""
        known_ids = {r.get("databaseId") for r in configured}
        known_wf = {r.get("workflowDatabaseId") for r in configured if r.get("workflowDatabaseId")}
        known_names = {str(r.get("workflowName")).lower() for r in configured if r.get("workflowName")}
        ignored = self._ignored_names()
        extra = []
        for r in everything:
            if not isinstance(r, dict) or not str(r.get("headSha", sha)).startswith(sha[:7]):
                continue
            name = str(r.get("workflowName") or "")
            if r.get("event") != "pull_request" or not name or r.get("databaseId") in known_ids \
                    or r.get("workflowDatabaseId") in known_wf or name.lower() in known_names \
                    or name.lower() in ignored:
                continue
            extra.append(dict(r, _workflow="extra:" + name))
        names = sorted({r["_workflow"] for r in extra})
        self._extra_required = names
        key = (train or {}).get("id") or sha
        if names and key not in self._extras_logged:
            self._extras_logged.add(key)
            self.out("train %s: extra workflows joined the required set: %s" %
                     ((train or {}).get("id") or sha[:7], ", ".join(n[6:] for n in names)))
        return extra

    def _ignored_names(self) -> set:
        """watcher.ignore_workflows as lower-case workflow names; a file entry is read as the `name:` of that file."""
        names = set()
        for item in C.ignore_workflows(self.cfg):
            names.add(item.lower())
            if item.lower().endswith((".yml", ".yaml")):
                names.add(Path(item).stem.lower())
                try:
                    text = (self.root / ".github" / "workflows" / item).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                m = re.search(r"""^name\s*:\s*["']?([^"'#\n]+?)["']?\s*(?:#.*)?$""", text, re.M)
                if m:
                    names.add(m.group(1).strip().lower())
        return names

    def ready_info(self, train: dict, head: str):
        """(is_draft, ready_at) for the train's PR. ready_at is the last ready_for_review event when there was
        one, else the PR's createdAt; None when unknown (then no run is dropped)."""
        pr = train.get("pr")
        data = self.gh_json(["pr", "view", str(pr), "--json", "createdAt,isDraft", *self.repo_args])
        if not isinstance(data, dict):
            return False, None
        draft = data.get("isDraft") is True
        ready = L.parse_iso(data.get("createdAt"))
        key = (pr, head)
        if key in self._ready_cache and not draft:
            return draft, self._ready_cache[key]
        rc, out, _ = self.read(["gh", "api", "repos/%s/issues/%s/timeline" % (self.repo or "{owner}/{repo}", pr),
                                "--paginate", "--jq", '.[] | select(.event=="ready_for_review") | .created_at'])
        if rc == 0:
            stamps = [L.parse_iso(x.strip().strip('"')) for x in (out or "").splitlines() if x.strip()]
            stamps = [x for x in stamps if x]
            if stamps:
                ready = max(stamps)
        if not draft:
            self._ready_cache[key] = ready
        return draft, ready

    def head_ci(self, train: dict, head: str):
        """(runs, state) for the train's head; (None, None) when gh failed. A PR that is still a draft is never green."""
        draft, ready = self.ready_info(train, head)
        runs = self.runs_for_commit(head, train, ready)
        if runs is None:
            return None, None
        state = ci_state_from_runs(runs, self.ci_required())
        if draft and state == "success":
            state = "queued"
        return runs, state

    def ci_required(self) -> list:
        """What must be green for a train: the workflow files (options a and b) and the commit-status contexts of
        the cloud shards (option c). The same rule for all three: the newest result of each is success (DL15)."""
        return self.workflows_needed() + list(self._extra_required) + C.cloud_contexts(self.root, self.cfg)

    def workflows_needed(self) -> list:
        """The workflow files to read. Empty when every chosen OS is cloud: option c uses no GitHub Actions."""
        opts = C.ci_options(self.cfg)
        if opts and all(v == "cloud" for v in opts.values()):
            return []
        if C._section(self.cfg, "watcher").get("ci_workflows"):
            return list(C.ci_workflows(self.cfg))   # the owner's list is the required set (DL-03)
        found = pr_workflows(self.root)
        # nothing configured: every workflow that runs on each pull-request commit; else the default guess
        return found or list(C.ci_workflows(self.cfg))

    def statuses_for_commit(self, sha: str, contexts: list):
        """Option c results as run-shaped rows, one per posted context; None when gh failed. A context with no status
        yet has no row, which the state rule reads as queued."""
        data = self.gh_json(["api", "repos/%s/commits/%s/status" % (self.repo or "{owner}/{repo}", sha)])
        if not isinstance(data, dict) or not isinstance(data.get("statuses"), list):
            return None
        out = []
        for st in data["statuses"]:
            if not isinstance(st, dict) or st.get("context") not in contexts:
                continue
            state = st.get("state")
            out.append({"_workflow": st["context"], "databaseId": st.get("id") or 0, "headSha": sha,
                        "status": "completed" if state in ("success", "failure", "error") else "in_progress",
                        "conclusion": "success" if state == "success" else "failure"})
        return out

    def cancel_superseded(self, train: dict, head: str) -> list[int]:
        data = self.gh_json(["run", "list", "--branch", train["branch"], "--workflow", WORKFLOW, "--limit", "50",
                             "--json", RUN_FIELDS, *self.repo_args]) or []
        done = []
        for r in data:
            if r.get("status") in ("queued", "in_progress", "waiting", "pending") and \
                    not str(r.get("headSha", "")).startswith(head[:7]):
                self.act(["gh", "run", "cancel", str(r["databaseId"]), *self.repo_args])
                done.append(r["databaseId"])
        if done:
            self.mut(lambda led: L.add_event(led, "ci.cancel_superseded", "%s %s" % (train["id"], done), "delivery_watch"))
        return done

    def adopt_pr(self, train: dict) -> bool:
        """DS95: a train pushed by hand whose pull request was opened (or made ready) before the
        train was known has no PR number, so its CI is never read. Adopt the one open pull
        request whose head is the train's branch; none or several: leave it."""
        if L.hold_active(train, self.now()):
            return False
        found = self.gh_json(["pr", "list", "--head", train["branch"], "--state", "open",
                              "--json", "number,headRefOid,isDraft", *self.repo_args])
        if not isinstance(found, list) or len(found) != 1 or not found[0].get("number"):
            return False
        pr = int(found[0]["number"])
        # DS97: results match by head from now on. CO688: a draft PR is adopted but does not start CI.
        self.mut(lambda led: L.adopt_open_pr(led, train["id"], found[0], "delivery_watch"))
        train["pr"] = pr
        return True

    def repoint_if_moved(self, train: dict) -> None:
        """CO688: a train that has a PR but has not reached `pushed` (the push happened where the hook could not see
        it, for example in a backgrounded command) is compared with the PR head; when they differ the train points
        at the PR head with empty runs, as `_rec_push` does for a re-push. pushed/ci/green/red trains are re-pointed
        by the rest of pass_trains."""
        data = self.gh_json(["pr", "view", str(train["pr"]), "--json", "headRefOid,state,isDraft", *self.repo_args])
        if not isinstance(data, dict) or not data.get("headRefOid") or data.get("state") == "MERGED":
            return
        head = data["headRefOid"]
        if head == (self._train_ci(train).get("head_sha")):
            return

        def fn(led):
            t = L.find_train(led, train["id"])
            if t is None or t.get("merged_at"):
                return
            if not isinstance(t.get("ci"), dict):
                t["ci"] = {}
            t["ci"].update({"head_sha": head, "run_ids": [], "state": "queued", "started_at": None})
            t["green_at"] = None
            if not data.get("isDraft") and t.get("state") in ("planned", "joining", "joined"):
                t["pushed_at"] = t.get("pushed_at") or L.iso(self.now())
                L.set_train_state(t, "ci", L.iso(self.now()))
            L.add_event(led, "train.repushed", t["id"], "delivery_watch")
        self.mut(fn)

    def pass_trains(self) -> None:
        led = L.load(self.root)
        for train in led["trains"]:
            # CO688: PR 847 sat in `planned` for ever because only pushed/ci trains were adopted
            adopted = False
            if train.get("state") in ("planned", "joining", "joined", "pushed", "ci", "red") and not train.get("pr"):
                adopted = self.adopt_pr(train)
                if adopted:
                    fresh = L.find_train(L.load(self.root), train["id"])
                    if fresh is not None:
                        train.clear()
                        train.update(fresh)
            if train.get("pr") and not adopted and train.get("state") in ("planned", "joining", "joined"):
                self.repoint_if_moved(train)
            if train.get("state") not in ("pushed", "ci", "green", "red") or not train.get("pr"):
                continue
            self._train_ci(train)
            if train.get("state") == "red":
                self._recheck_red(train)
                continue
            head, pr_state = self.current_head(train)
            if not head:
                continue
            if pr_state == "MERGED":
                self._set_train(train, "merged", ci=None)
                continue
            if self.rp["cancel_replaced_runs"]:
                self.cancel_superseded(train, head)
            runs, state = self.head_ci(train, head)
            if runs is None:
                continue
            ci = {"head_sha": head, "run_ids": [r["databaseId"] for r in runs], "state": state, **ci_wall(runs, state)}
            if state == "success" and train.get("state") != "green":
                self._set_train(train, "green", ci=ci)
            elif state == "failure" and train.get("state") != "red":
                self._set_train(train, "red", ci=ci)
            elif state in ("running", "queued") and train.get("state") == "green":
                self._revoke_green(train, ci)     # a required run is not done: not green (DL-03)
            else:
                self._set_train(train, None, ci=ci)
            if state == "success" and self.flags["merge_on_green"]:
                self.maybe_merge(train, head)

    def _train_ci(self, train: dict) -> dict:
        """The train's ci block as a dict. A ledger row whose ci is not a dict (a string was seen in the wild)
        is treated as unknown, logged once per train, and read as empty; it never raises."""
        ci = train.get("ci")
        if isinstance(ci, dict):
            return ci
        if ci is not None and train.get("id") not in self._bad_ci_logged:
            self._bad_ci_logged.add(train.get("id"))
            self.out("train %s: ci is %s, not a dict; treated as unknown" % (train.get("id"), type(ci).__name__))
        return {}

    def _recheck_red(self, train: dict) -> None:
        """A red train leaves red when the runs of its head commit conclude green for every required workflow
        (the owner re-ran a failed run: same run id, newer attempt, or a new run), or when the branch head moved
        (a fix was pushed): the train is re-pointed to the new head and judged by that head's runs. One cheap
        check per cycle; a still-failing or missing run on the same head writes nothing. Green takes the normal
        path (merge on green, never --auto)."""
        stored = self._train_ci(train).get("head_sha")
        head, pr_state = self.current_head(train)
        if pr_state == "MERGED":
            self._set_train(train, "merged", ci=None)
            return
        if not head:
            return
        moved = head != stored
        runs, state = self.head_ci(train, head)
        if runs is None:
            return
        if not moved and state != "success":
            return
        ci = {"head_sha": head, "run_ids": [r["databaseId"] for r in runs], "state": state, **ci_wall(runs, state)}
        if state == "success":
            self._set_train(train, "green", ci=ci)
            if self.flags["merge_on_green"]:
                self.maybe_merge(train, head)
        elif state == "failure":
            self._set_train(train, None, ci=ci)         # red on the new head: stays red, now pointing at it
        else:
            self._set_train(train, "ci", ci=ci)         # the new head's runs are queued or running

    def _revoke_green(self, train: dict, ci: dict) -> None:
        def fn(led):
            t = L.find_train(led, train["id"])
            if t is None or t.get("merged_at"):
                return
            if not isinstance(t.get("ci"), dict):
                t["ci"] = {}
            t["ci"].update(ci)
            t["state"], t["green_at"] = "ci", None
            L.add_event(led, "train.green_revoked", t["id"], "delivery_watch")
        self.mut(fn)
        train["state"] = "ci"

    def _set_train(self, train: dict, state, ci=None) -> None:
        def fn(led):
            t = L.find_train(led, train["id"])
            if t is None:
                return
            if ci is not None:
                if not isinstance(t.get("ci"), dict):
                    t["ci"] = {}
                prev = t["ci"].get("head_sha")
                t["ci"].update(ci)
                if prev != ci.get("head_sha") or not t["ci"].get("started_at"):
                    t["ci"]["started_at"] = L.iso(self.now())
            if state and t.get("state") != state:
                L.set_train_state(t, state, L.iso(self.now()))
                L.add_event(led, "train.%s" % state, t["id"], "delivery_watch")
        self.mut(fn)
        if state:
            train["state"] = state

    def maybe_merge(self, train: dict, head: str) -> bool:
        """D5: merge at green on the current head, unless held. Never --auto."""
        fresh = L.find_train(L.load(self.root), train["id"]) or train
        if L.hold_active(fresh, self.now()):
            return False
        if self.cfg.get("measure_globs") and fresh.get("measure", {}).get("state") == "regressions":
            return False
        now_head, _ = self.current_head(train)
        if now_head != head:    # D5: only the commit whose CI was green is merged
            self.mut(lambda led: L.add_event(led, "merge.head_moved", "%s %s -> %s" % (
                train["id"], head[:7], (now_head or "?")[:7]), "delivery_watch"))
            return False
        rc, out, err = self.act(["gh", "pr", "merge", str(train["pr"]), "--merge", "--match-head-commit", head,
                                 *self.repo_args])
        if rc != 0:
            self.mut(lambda led: L.add_event(led, "merge.failed", "%s %s" % (train["id"], (err or out).strip()[:120]),
                                             "delivery_watch"))
            return False
        self._set_train(train, "merged")
        self.push_next(exclude=train["id"])
        return True

    def pr_body(self, train) -> str:
        """The ready PR body: the train line, then .delivery/docs-summaries.md when join.py wrote it (DOCSPEC R10.3,
        the summaries of the agent reports it stripped). A missing or unreadable file adds nothing."""
        body = "Train %s: %s" % (train["id"], ", ".join(c.get("task", "") for c in train.get("cargo", [])))
        try:
            extra = (self.root / DOCS_SUMMARIES).read_text(encoding="utf-8").strip()
        except OSError:
            extra = ""
        return body + ("\n\n" + extra if extra else "")

    def push_next(self, exclude=None) -> None:
        """Push the next joined train and open its ready PR (not while another train's CI runs)."""
        if not self.flags["push_trains"]:
            return
        led = L.load(self.root)
        busy = [t for t in led["trains"] if t["id"] != exclude and t.get("state") in ACTIVE_CI_STATES + ("green",)]
        if busy:
            return
        nxt = next((t for t in led["trains"] if t.get("state") == "joined" and not L.hold_active(t, self.now())), None)
        if nxt is None:
            return
        b = nxt["branch"]
        rc, _, err = self.act(["git", "push", "origin", "refs/heads/%s:refs/heads/%s" % (b, b)])
        if rc != 0:
            self.mut(lambda l2: L.add_event(l2, "push.failed", "%s %s" % (nxt["id"], err.strip()[:120]), "delivery_watch"))
            return
        self.mut(lambda l2: _stamp(l2, nxt["id"], "pushed", self.now()))
        pr = nxt.get("pr")
        if not pr:
            found = self.gh_json(["pr", "list", "--head", b, "--state", "open", "--json", "number", *self.repo_args])
            pr = found[0]["number"] if isinstance(found, list) and found else None
        if not pr and self.flags["open_prs"]:
            title = "Release %s" % (nxt.get("release_no") or b)
            body = self.pr_body(nxt)
            rc, out, _ = self.act(["gh", "pr", "create", "--base", self.cfg.get("base", "main"), "--head", b,
                                   "--title", title, "--body", body, *self.repo_args])
            m = re.search(r"/pull/(\d+)", out or "")
            pr = int(m.group(1)) if rc == 0 and m else None
        if pr:
            def fn(l2):
                t = L.find_train(l2, nxt["id"])
                if t is not None:
                    t["pr"] = pr
                    L.set_train_state(t, "ci", L.iso(self.now()))
                    L.add_event(l2, "train.next_pushed", t["id"], "delivery_watch")
            self.mut(fn)

    # -- other CI runs --
    def pass_other_runs(self) -> None:
        led = L.load(self.root)
        train_branches = {t["branch"] for t in led["trains"]}
        base = self.cfg.get("base", "main")
        ci_running = any(t.get("state") in ACTIVE_CI_STATES for t in led["trains"]) and \
            self.rp["hold_dependabot_during_train"]
        seen = {h.get("id") for h in led.get("held_runs", [])}
        if ci_running:
            for status in ("in_progress", "queued"):
                data = self.gh_json(["run", "list", "--status", status, "--limit", "50", "--json", RUN_FIELDS,
                                     *self.repo_args]) or []
                for r in data:
                    br = r.get("headBranch")
                    if not br or br in train_branches or br == base:
                        continue
                    if r["databaseId"] in seen:
                        continue
                    seen.add(r["databaseId"])
                    rc, _, _ = self.act(["gh", "run", "cancel", str(r["databaseId"]), *self.repo_args])
                    if rc == 0:
                        row = {"id": r["databaseId"], "branch": br, "sha": r.get("headSha"), "at": L.iso(self.now()),
                               "state": "held"}  # DL249: a held run is not a failure
                        print("delivery_watch: HELD run %s on %s (cancelled on purpose while a train's CI runs; "
                              "it is re-run when that CI ends; not a failure)" % (row["id"], br), flush=True)
                        self.mut(lambda l2, row=row: (l2.setdefault("held_runs", []).append(row),
                                                      L.add_event(l2, "ci.hold", "%s %s" % (row["branch"], row["id"]), "delivery_watch")))
        else:
            for h in led.get("held_runs", []):
                print("delivery_watch: re-running held run %s on %s" % (h["id"], h.get("branch")), flush=True)
                self.act(["gh", "run", "rerun", str(h["id"]), *self.repo_args])
            if led.get("held_runs"):
                n = len(led["held_runs"])
                self.mut(lambda l2: (l2.__setitem__("held_runs", []), L.add_event(l2, "ci.rerun_held", str(n), "delivery_watch")))

    # -- installs, runners, heartbeat --
    def pass_installs(self) -> None:
        for spec in self.cfg.get("install_state_files", []) or []:
            try:
                data = json.loads(Path(spec["path"]).read_text(encoding="utf-8"))
            except (OSError, ValueError, KeyError):
                continue
            if not isinstance(data, dict):
                continue
            product = spec.get("product")

            def fn(led, product=product, data=data):
                row = next((i for i in reversed(led["installs"]) if i.get("product") == product), None)
                if row is None:
                    row = {"product": product, "version": None, "via": "state-file", "state": "queued",
                           "started": None, "ended": None, "log": None}
                    led["installs"].append(row)
                for k in ("version", "state", "started", "ended", "log"):
                    if data.get(k) is not None:
                        row[k] = data[k]
            self.mut(fn)

    def pass_runners(self) -> None:
        data = self.gh_json(["api", "repos/%s/actions/runners" % (self.repo or "{owner}/{repo}")])
        if not isinstance(data, dict):
            return
        local = set(self.cfg.get("local_runners", []) or [])
        at = L.iso(self.now())

        def fn(led):
            old = {r.get("name"): r for r in led["runners"]}
            led["runners"] = [{
                "name": r.get("name"), "labels": [l.get("name") for l in r.get("labels", [])],
                "online": r.get("status") == "online", "busy": bool(r.get("busy")),
                "local": r.get("name") in local, "paused_by": (old.get(r.get("name")) or {}).get("paused_by"),
                "checked_at": at} for r in data.get("runners", [])]
        self.mut(fn)

    def runner_script(self):
        rp = self.cfg.get("runner_plan") if isinstance(self.cfg.get("runner_plan"), dict) else {}
        for c in (os.environ.get("DELIVERY_RUNNER_PLAN"), rp.get("script"), os.path.join("scripts", "delivery", "runner_plan.py")):
            if c:
                path = c if os.path.isabs(c) else str(self.root / c)
                if not os.path.isfile(path):
                    continue
                real, base = os.path.realpath(path), os.path.realpath(str(self.root))
                if real != base and not real.startswith(base + os.sep):
                    self.out(f"delivery_watch: refusing runner_plan script {c!r}: it resolves outside the repository root")
                    continue
                return path
        return None

    def pass_runner_guard(self) -> None:
        """D6a: keep `runner_plan.py runners` running; it reports an offline runner, repairs it every
        retry_seconds and re-runs the CI the outage cost. Not launched without runners[] in the config."""
        if not self.flags["manage_runners"] or not self.cfg.get("runners"):
            return
        if self.runner_child is not None:
            code = self.runner_child.poll()
            if code is None:
                return
            if code != 0:
                self.mut(lambda led: L.add_event(led, "runner.guard_exit", "exit %s" % code, "delivery_watch"))
            self.runner_child = None
        script = self.runner_script()
        if script is None:
            if not self._guard_missing_logged:
                self._guard_missing_logged = True
                self.out("delivery_watch: runners[] is configured but runner_plan.py was not found "
                         "(scripts/delivery/runner_plan.py or runner_plan.script)")
                self.mut(lambda led: L.add_event(led, "runner.guard_missing", "runner_plan.py not found", "delivery_watch"))
            return
        argv = [sys.executable, script, "runners", "--root", str(self.root), *self.repo_args]
        self.actions.append(argv)
        if self.dry:
            self.out("dry-run: " + " ".join(argv))
            return
        self.runner_child = self.sh.spawn(argv, cwd=str(self.root))
        if not self._guard_start_logged:         # CO688: it exits at once while the runners are online and is
            self._guard_start_logged = True      # relaunched every pass: one event, not 239 of the 500 kept
            self.mut(lambda led: L.add_event(led, "runner.guard_started", os.path.basename(script), "delivery_watch"))

    def pass_ci_runs(self) -> None:
        """D48: refresh .delivery/ci-runs.json for the Full Progress CI runs section, at most once a minute.
        A failure leaves the old file and never fails the tick."""
        if self.dry or not self.ci_runs:
            return
        path = self.root / CR.OUT_REL
        try:
            if time.time() - path.stat().st_mtime < CI_RUNS_MIN_INTERVAL_S:
                return
        except OSError:
            pass
        col = CR.Collector(self.root, repo=self.repo, sh=self.sh, now=self.now)
        doc = col.collect()
        if doc is not None:
            col.write(doc)

    def heartbeat(self, started: str) -> None:
        pid, at = os.getpid(), L.iso(self.now())

        def fn(led):
            led["watchers"] = [w for w in led["watchers"] if w.get("pid") != pid]
            led["watchers"].append({"pid": pid, "kind": "delivery_watch", "started": started, "heartbeat_at": at,
                                    "version": WATCHER_VERSION})
            import machine_slots as M
            L.prune_watchers(led, self.now(), M.pid_alive)      # DL118
        self.mut(fn)

    def run_once(self, started: str | None = None) -> list[list[str]]:
        self.actions = []
        for step in (self.pass_agents, self.pass_checks, self.pass_trains, self.pass_other_runs, self.pass_installs, self.pass_runners,
                     self.pass_runner_guard, self.pass_ci_runs):
            try:
                step()
            except Exception as exc:  # noqa: BLE001 - one failing pass never stops the others
                self.out("delivery_watch: %s failed: %s" % (step.__name__, exc))
        self.heartbeat(started or L.iso(self.now()))
        return self.actions


# DL98: the plugin version this process started with, read once (the file on disk changes on an upgrade)
WATCHER_VERSION = L.plugin_version()


def _stamp(led, train_id, state, now):
    t = L.find_train(led, train_id)
    if t is not None:
        L.set_train_state(t, state, L.iso(now))
        L.add_event(led, "train.%s" % state, train_id, "delivery_watch")


def live_peer(led, interval: float, now=None, pid=None, alive=None):
    """DL109: another delivery_watch for this root that is still running: its pid is alive, its heartbeat is newer than
    three intervals, and its plugin version is not older than ours. A second watcher then exits."""
    import machine_slots as M
    alive = alive or M.pid_alive
    pid = pid or os.getpid()
    now = now or L.utcnow()
    mine = L.version_key(WATCHER_VERSION)
    for w in led.get("watchers") or []:
        other = w.get("pid")
        if w.get("kind") != "delivery_watch" or not isinstance(other, int) or other == pid:
            continue
        beat = L.parse_iso(w.get("heartbeat_at"))
        if beat is None or (now - beat).total_seconds() > 3 * interval:
            continue
        if mine and L.version_key(w.get("version")) < mine:
            continue
        if alive(other):
            return w
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", help="repository root (default: nearest with .delivery/)")
    ap.add_argument("--interval", type=float, help="seconds between passes (default: config watch_interval or 60)")
    ap.add_argument("--once", action="store_true", help="a single pass, then exit")
    ap.add_argument("--dry-run", action="store_true", help="print the actions; perform none, write nothing")
    ap.add_argument("--repo", help="OWNER/NAME for gh (default: the current repository)")
    args = ap.parse_args(argv)
    root = Path(args.root) if args.root else L.find_root()
    if root is None or not (root / L.DIR_NAME).is_dir():
        print("delivery_watch: no .delivery/ folder found", file=sys.stderr)
        return 2
    w = Watcher(root, dry_run=args.dry_run, repo=args.repo)
    interval = args.interval or float(w.cfg.get("watch_interval") or w.cfg.get("watcher_interval_s") or DEFAULT_INTERVAL)
    started = L.iso()
    if not args.once and not args.dry_run:
        peer = live_peer(L.load(root), interval)
        if peer:
            print("delivery_watch: pid %s already watches %s; this one exits" % (peer.get("pid"), root), file=sys.stderr)
            return 0
    while True:
        w.run_once(started)
        if args.once:
            return 0
        time.sleep(max(1.0, interval))


if __name__ == "__main__":
    sys.exit(main())
