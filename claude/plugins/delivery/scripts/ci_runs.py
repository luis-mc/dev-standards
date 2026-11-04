#!/usr/bin/env python3
"""CI runs for Full Progress (owner decision D48; contract: shared-self-hosted-runners.md sections 11, 12.2, 12.5).

    ci_runs.py collect --root .        writes .delivery/ci-runs.json

Data: GitHub Actions runs and jobs (`gh api`, steps carry started_at and completed_at), the slot log that the
machine layer writes (section 12.2), and the `ci-claim` markers for runs that fell back to the cloud.
Standard library only. `gh` and `git` go through one seam (`Shell`) so tests run on recorded JSON.
Reads only; it never changes a run, a branch or a marker.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT_REL = os.path.join(".delivery", "ci-runs.json")
FINISHED_SHOWN = 20
RUNS_PER_PAGE = 40
ACTIVE_STATES = ("queued", "in_progress", "waiting", "pending", "requested")
AGENT_BRANCH = re.compile(r"^(claude/|[A-Za-z]+\d+[-/])")
DEFAULT_MACHINE_DIR = {"nt": r"C:\ProgramData\luismc-delivery"}


class Shell:
    """The one seam for gh and git: run(argv, cwd) -> (returncode, stdout, stderr)."""

    def run(self, argv, cwd=None, timeout=60):
        try:
            p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except (OSError, subprocess.SubprocessError) as exc:
            return 127, "", str(exc)


# --- small helpers -------------------------------------------------------------------------------------------------

def parse_time(text):
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds(a, b):
    """Whole seconds from a to b, never negative; None when either is missing."""
    if a is None or b is None:
        return None
    return max(0, int(round((b - a).total_seconds())))


def machine_dir() -> str:
    """The machine layer's folder; asks machine_slots when it exists (section 12.2)."""
    env = os.environ.get("DELIVERY_MACHINE_DIR")
    if env:
        return env
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import machine_slots  # type: ignore  # noqa: WPS433
        return str(machine_slots.machine_dir())
    except Exception:  # noqa: BLE001 - the module may not exist yet
        return DEFAULT_MACHINE_DIR.get(os.name, "/etc/luismc-delivery")


# --- slot log (section 12.2) ---------------------------------------------------------------------------------------

def read_slot_log(path) -> dict:
    """{(repo, run_id, run_attempt, job): {"queued_at", "slot_at", "released_at", "outcome", "runner", "slot"}}.
    The machine layer writes separate lines for the take and the free; they are joined by the key. A bad line is skipped."""
    out: dict = {}
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("run_id") is None:
            continue
        key = (row.get("repo"), int(row["run_id"]), int(row.get("run_attempt") or 1), row.get("job"))
        merged = out.setdefault(key, {})
        for field in ("queued_at", "slot_at", "released_at", "outcome", "runner", "slot", "shard"):
            if row.get(field) is not None:
                merged[field] = row[field]
    return out


def slot_rows(slots: dict, repo, run_id, attempt) -> list:
    return [dict(v, job=k[3]) for k, v in slots.items() if k[0] == repo and k[1] == run_id and k[2] == attempt]


# --- why and where -------------------------------------------------------------------------------------------------

def why_of(run: dict, default_branch: str, fallback_wait_min=None) -> str:
    """The trigger in plain words (section 11)."""
    attempt = int(run.get("run_attempt") or 1)
    event, branch = run.get("event"), run.get("head_branch") or ""
    if fallback_wait_min is not None:
        return "fallback to cloud after %d min" % int(round(fallback_wait_min))
    if attempt > 1:
        return "re-run #%d by the owner" % attempt
    if event == "pull_request":
        prs = run.get("pull_requests") or []
        return "ready PR #%s" % prs[0]["number"] if prs and prs[0].get("number") else "ready PR"
    if event == "push":
        if branch == default_branch:
            return "push to %s" % default_branch
        return "agent branch %s" % branch if AGENT_BRANCH.match(branch) else "push to %s" % branch
    if event == "schedule":
        return "schedule"
    if event in ("workflow_dispatch", "repository_dispatch"):
        return "started by hand"
    return str(event or "unknown")


def where_of(jobs: list) -> dict:
    """The runner kind and name of the first job that has a runner (section 11)."""
    for job in jobs:
        name = job.get("runner_name") or ""
        labels = [str(x).lower() for x in (job.get("labels") or [])]
        if not name and not labels:
            continue
        if "self-hosted" in labels:
            kind = "windows" if "windows" in labels else "pool"
        else:
            kind = "hosted"
        return {"kind": kind, "name": name or ("GitHub-hosted" if kind == "hosted" else "")}
    return {"kind": "hosted", "name": "GitHub-hosted"}


# --- one run -------------------------------------------------------------------------------------------------------

def run_start(run: dict):
    return parse_time(run.get("run_started_at")) or parse_time(run.get("created_at"))


def build_finished(run: dict, jobs: list, slot_rows_: list, default_branch: str, repo: str, claim=None) -> dict:
    t0 = run_start(run)
    starts = [parse_time(j.get("started_at")) for j in jobs if parse_time(j.get("started_at"))]
    ends = [parse_time(j.get("completed_at")) for j in jobs if parse_time(j.get("completed_at"))]
    end = max(ends) if ends else parse_time(run.get("updated_at"))
    queued_s = seconds(t0, min(starts)) if starts else 0
    # the slot wait of each job, from the slot log
    waits, fallback_min, lost = [], None, False
    slot_start_s = None
    slot_end = None
    for row in slot_rows_:
        q, s = parse_time(row.get("queued_at")), parse_time(row.get("slot_at"))
        if q and s:
            waits.append(seconds(q, s))
            if slot_start_s is None or seconds(t0, q) < slot_start_s:
                slot_start_s = seconds(t0, q)
            slot_end = s if slot_end is None or s > slot_end else slot_end
        if row.get("outcome") == "claim-lost":
            lost = True
            fallback_min = (seconds(q, s) or 0) / 60.0 if q and s else None
    steps = []
    for job in jobs:
        for step in job.get("steps") or []:
            a, b = parse_time(step.get("started_at")), parse_time(step.get("completed_at"))
            if a is None or b is None or step.get("conclusion") == "skipped":
                continue
            if slot_end and a < slot_end:                     # the gate runs inside "Set up job": draw it once
                a = min(slot_end, b)
            steps.append({"job": job.get("name"), "name": step.get("name"), "start_s": seconds(t0, a),
                          "duration_s": seconds(a, b), "conclusion": step.get("conclusion") or "success"})
    conclusion = run.get("conclusion") or "cancelled"
    conclusion = "failure" if conclusion in ("failure", "timed_out", "startup_failure") else (
        conclusion if conclusion in ("success", "failure", "cancelled") else "cancelled")
    where = where_of(jobs)
    if lost or claim:
        where = {"kind": "cloud", "name": (claim or {}).get("holder") or "Claude cloud"}
    entry = {"run_id": run.get("id"), "workflow": run.get("name") or "", "conclusion": conclusion,
             "run_number": run.get("run_number"), "run_attempt": int(run.get("run_attempt") or 1),
             "why": why_of(run, default_branch, fallback_min if lost else None), "where": where,
             "queued_s": queued_s or 0, "slot_wait_s": sum(waits) if waits else 0,
             "total_s": seconds(t0, end) or 0, "completed_at": iso(end) if end else None, "steps": steps}
    if slot_start_s is not None:
        entry["slot_start_s"] = slot_start_s
    if lost:
        entry["fallback"] = True
    return entry


def build_active(run: dict, jobs: list, slot_rows_: list, default_branch: str, now: datetime, after_min) -> dict:
    where = where_of(jobs)
    now_info, slot_wait = None, None
    for job in jobs:
        for step in job.get("steps") or []:
            if step.get("status") == "in_progress":
                now_info = {"step": step.get("name"), "since": step.get("started_at")}
    for row in slot_rows_:
        if row.get("queued_at") and not row.get("slot_at"):
            since = parse_time(row["queued_at"])
            waited = (now - since).total_seconds() / 60.0 if since else 0
            left = None if after_min is None else max(0, int(round(after_min - waited)))
            slot_wait = {"since": row["queued_at"], "fallback_in_min": left}
            now_info = None
    if now_info is None and slot_wait is None and any(j.get("status") == "in_progress" for j in jobs):
        now_info = {"step": "starting", "since": run.get("run_started_at") or run.get("created_at")}
    entry = {"run_id": run.get("id"), "workflow": run.get("name") or "", "run_number": run.get("run_number"),
             "why": why_of(run, default_branch), "where": where,
             "started_at": run.get("run_started_at") or run.get("created_at"), "now": now_info}
    if slot_wait:
        entry["slot_wait"] = slot_wait
    return entry


# --- gh and git ----------------------------------------------------------------------------------------------------

class Collector:
    def __init__(self, root, repo=None, sh=None, now=None, slot_log=None, claims=None):
        self.root = Path(root)
        self.sh = sh or Shell()
        self.repo = repo
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.slot_log = slot_log if slot_log is not None else os.path.join(machine_dir(), "slot-log.jsonl")
        self.claims = claims or self.default_claims

    def gh(self, endpoint):
        rc, out, _ = self.sh.run(["gh", "api", endpoint], cwd=str(self.root))
        if rc != 0:
            return None
        try:
            return json.loads(out or "null")
        except ValueError:
            return None

    def find_repo(self):
        if self.repo:
            return self.repo
        rc, out, _ = self.sh.run(["git", "remote", "get-url", "origin"], cwd=str(self.root))
        m = re.search(r"github\.com[:/]+([^/\s]+/[^/\s]+?)(?:\.git)?\s*$", out or "") if rc == 0 else None
        self.repo = m.group(1) if m else None
        return self.repo

    def after_min(self):
        try:
            cfg = json.loads((self.root / ".delivery" / "config.json").read_text(encoding="utf-8"))
            val = ((cfg.get("ci") or {}).get("fallback") or {}).get("after_min")
            return float(val) if val is not None else None
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def default_claims(self, sha):
        """[{holder, shard, attempt, at}] of the ci-claim markers of `sha` (read only), or []."""
        rc, out, _ = self.sh.run(["git", "ls-remote", "--heads", "origin", "refs/heads/ci-claim/%s/*" % sha], cwd=str(self.root))
        found = []
        for line in (out or "").splitlines() if rc == 0 else []:
            ref = line.partition("\t")[2]
            if not ref:
                continue
            local = "refs/ci-runs-fetched/" + ref[len("refs/heads/"):]
            if self.sh.run(["git", "fetch", "-q", "origin", "+%s:%s" % (ref, local)], cwd=str(self.root))[0]:
                continue
            rc2, body, _ = self.sh.run(["git", "log", "-1", "--format=%B", local], cwd=str(self.root))
            try:
                data = json.loads(body)
            except ValueError:
                continue
            if rc2 == 0 and isinstance(data, dict):
                found.append(data)
        return found

    def previous(self) -> dict:
        try:
            data = json.loads((self.root / OUT_REL).read_text(encoding="utf-8"))
            return {(e.get("run_id"), e.get("run_attempt", 1)): e for e in data.get("finished", [])}
        except (OSError, ValueError, AttributeError):
            return {}

    def collect(self):
        """The ci-runs.json document, or None when GitHub could not be read (the old file stays)."""
        repo = self.find_repo()
        if not repo:
            return None
        meta = self.gh("repos/%s" % repo) or {}
        default_branch = meta.get("default_branch") or "main"
        listing = self.gh("repos/%s/actions/runs?per_page=%d" % (repo, RUNS_PER_PAGE))
        if not isinstance(listing, dict):
            return None
        runs = listing.get("workflow_runs") or []
        slots = read_slot_log(self.slot_log)
        now, after, cache = self._now(), self.after_min(), self.previous()

        def jobs_of(run):
            data = self.gh("repos/%s/actions/runs/%s/jobs?per_page=100&filter=latest" % (repo, run["id"]))
            return (data or {}).get("jobs") or [] if isinstance(data, dict) else []

        active = []
        for run in runs:
            if run.get("status") in ACTIVE_STATES:
                active.append(build_active(run, jobs_of(run), slot_rows(slots, repo, run["id"], int(run.get("run_attempt") or 1)),
                                           default_branch, now, after))
        done = [r for r in runs if r.get("status") == "completed" and r.get("conclusion") != "skipped"]
        done.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
        finished = []
        for run in done[:FINISHED_SHOWN]:
            attempt = int(run.get("run_attempt") or 1)
            if (run["id"], attempt) in cache:
                finished.append(cache[(run["id"], attempt)])
                continue
            rows = slot_rows(slots, repo, run["id"], attempt)
            claim = None
            if any(r.get("outcome") == "claim-lost" for r in rows):
                held = [c for c in self.claims(run.get("head_sha")) if c.get("holder")]
                claim = held[-1] if held else None
            finished.append(build_finished(run, jobs_of(run), rows, default_branch, repo, claim))
        return {"generated_at": iso(now), "repo": repo, "active": active, "finished": finished}

    def write(self, doc) -> None:
        path = self.root / OUT_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(path))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write .delivery/ci-runs.json (CI runs for Full Progress).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--root", default=".")
    c.add_argument("--repo", help="owner/name; default: the origin remote")
    c.add_argument("--slot-log", help="path of slot-log.jsonl; default: the machine folder")
    a = ap.parse_args(argv)
    col = Collector(a.root, repo=a.repo, slot_log=a.slot_log)
    doc = col.collect()
    if doc is None:
        print("ci_runs: GitHub could not be read; %s left as it was" % OUT_REL, file=sys.stderr)
        return 1
    col.write(doc)
    print("ci_runs: %d active, %d finished -> %s" % (len(doc["active"]), len(doc["finished"]), OUT_REL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
