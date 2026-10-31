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

DEFAULT_INTERVAL = 60
WORKFLOW = "ci.yml"
ACTIVE_CI_STATES = ("pushed", "ci")
RUN_FIELDS = "databaseId,status,conclusion,headSha,headBranch,event,workflowName"


class Shell:
    """The one seam for gh and git. run(argv, cwd) -> (returncode, stdout, stderr)."""

    def run(self, argv: list[str], cwd=None, timeout: int = 120):
        try:
            p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except (OSError, subprocess.SubprocessError) as exc:
            return 127, "", str(exc)

    def spawn(self, argv: list[str], cwd=None):
        """Start a long-running child without waiting; None when it cannot start."""
        try:
            return subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except OSError:
            return None


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
    if any(r.get("conclusion") != "success" for r in mine):
        return "failure"
    if len(mine) < len(required):
        return "queued" if not mine else "running"
    return "success"


class Watcher:
    def __init__(self, root, sh=None, dry_run=False, now=None, routine_fetcher=None,
                 out=print, repo=None):
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
        self.repo = repo
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
        for idx, a in enumerate(led["agents"]):
            if a.get("state") not in ("queued", "running", "pushed", "stalled"):
                continue
            changes: dict = {}
            activity = L.parse_iso(a.get("last_activity")) or L.parse_iso(a.get("started"))
            branch = a.get("branch")
            if branch and a.get("where") != "cloud-skip":
                rc, out, _ = self.read(["git", "ls-remote", "origin", "refs/heads/%s" % branch])
                sha = out.split()[0] if rc == 0 and out.strip() else None
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
            if changes:
                self._apply_agent(idx, a, changes)

    def _apply_agent(self, idx: int, before: dict, changes: dict) -> None:
        def fn(led):
            row = next((x for x in led["agents"] if x.get("id") == before.get("id") and
                        x.get("branch") == before.get("branch") and x.get("task") == before.get("task")), None)
            if row is None:
                return
            if changes.get("state") and changes["state"] != row.get("state"):
                L.add_event(led, "agent.%s" % changes["state"], str(row.get("task") or row.get("id")), "delivery_watch")
            row.update(changes)
        self.mut(fn)
        if self.dry:
            self.out("dry-run: agent %s -> %s" % (before.get("task"), changes))

    # -- trains --
    def current_head(self, train: dict):
        pr = train.get("pr")
        data = self.gh_json(["pr", "view", str(pr), "--json", "headRefOid,state", *self.repo_args])
        if not isinstance(data, dict):
            return None, None
        return data.get("headRefOid"), data.get("state")

    def runs_for_commit(self, sha: str):
        """The runs of every required workflow (watcher.ci_workflows) for one commit; None when gh failed."""
        out = []
        for wf in C.ci_workflows(self.cfg):
            data = self.gh_json(["run", "list", "--commit", sha, "--workflow", wf, "--limit", "100",
                                 "--json", RUN_FIELDS, *self.repo_args])
            if not isinstance(data, list):
                return None
            out += [dict(r, _workflow=wf) for r in data
                    if isinstance(r, dict) and str(r.get("headSha", sha)).startswith(sha[:7])]
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
            runs = self.runs_for_commit(head)
            if runs is None:
                continue
            state = ci_state_from_runs(runs, C.ci_workflows(self.cfg))
            ci = {"head_sha": head, "run_ids": [r["databaseId"] for r in runs], "state": state}
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
        runs = self.runs_for_commit(head)
        if runs is None:
            return
        state = ci_state_from_runs(runs, C.ci_workflows(self.cfg))
        if not moved and state != "success":
            return
        ci = {"head_sha": head, "run_ids": [r["databaseId"] for r in runs], "state": state}
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
            body = "Train %s: %s" % (nxt["id"], ", ".join(c.get("task", "") for c in nxt.get("cargo", [])))
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
                        row = {"id": r["databaseId"], "branch": br, "sha": r.get("headSha"), "at": L.iso(self.now())}
                        self.mut(lambda l2, row=row: (l2.setdefault("held_runs", []).append(row),
                                                      L.add_event(l2, "ci.hold", "%s %s" % (row["branch"], row["id"]), "delivery_watch")))
        else:
            for h in led.get("held_runs", []):
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
                if os.path.isfile(path):
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

    def heartbeat(self, started: str) -> None:
        pid, at = os.getpid(), L.iso(self.now())

        def fn(led):
            led["watchers"] = [w for w in led["watchers"] if w.get("pid") != pid]
            led["watchers"].append({"pid": pid, "kind": "delivery_watch", "started": started, "heartbeat_at": at})
        self.mut(fn)

    def run_once(self, started: str | None = None) -> list[list[str]]:
        self.actions = []
        for step in (self.pass_agents, self.pass_trains, self.pass_other_runs, self.pass_installs, self.pass_runners,
                     self.pass_runner_guard):
            try:
                step()
            except Exception as exc:  # noqa: BLE001 - one failing pass never stops the others
                self.out("delivery_watch: %s failed: %s" % (step.__name__, exc))
        self.heartbeat(started or L.iso(self.now()))
        return self.actions


def _stamp(led, train_id, state, now):
    t = L.find_train(led, train_id)
    if t is not None:
        L.set_train_state(t, state, L.iso(now))
        L.add_event(led, "train.%s" % state, train_id, "delivery_watch")


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
    while True:
        w.run_once(started)
        if args.once:
            return 0
        time.sleep(max(1.0, interval))


if __name__ == "__main__":
    sys.exit(main())
