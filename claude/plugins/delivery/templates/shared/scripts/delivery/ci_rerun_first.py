#!/usr/bin/env python3
"""Run first the CI jobs that have not passed yet (DL181, DL-80 family).

    ci_rerun_first.py --repo OWNER/REPO --workflow ci.yml --branch BR --sha HEAD
                      [--only a,b] [--selected a,b] [--config FILE] [--json]

Rule: a new push to a branch whose previous head already had a run of the same workflow starts with the
jobs that failed, were cancelled, timed out, or were skipped or absent while selected on that run. The jobs
that passed there come after, so a new failure shows sooner. A first run behaves as today.

GitHub `needs` is static, so one run cannot reorder its jobs. The workflow holds back the HOLDABLE jobs
that passed before (`held`), runs the rest, and a last job dispatches a second run with `--only` naming
the held jobs. `verify` is never held: it always runs.

Opt in with `"rerun_first": true` in scripts/delivery/ci-areas.json (or --config FILE). Off or missing: `rerun=false`.

Outputs (to $GITHUB_OUTPUT, appended; stdout with --json, always printed as lines otherwise):
  rerun=true|false    true only when at least one job is held back
  first=<json list>   job keys that did not pass on the previous head (or --only)
  held=a,b            job keys held back for the second run (empty when rerun=false)
  reason=...          one line

DL183: while jobs are held, the commit carries the status `rerun-first/held` (pending). `--hold-status` sets it
as the plan decides to hold (if it cannot be set, nothing is held: every job runs). `--set-status STATE` sets
it later: success / failure / error. A project that does not opt in never gets the status.

Job names from the API map to job keys: a matrix leg ("web E2E shard 2", "build (3)") collapses to its base
name, then NAME_KEYS maps a display-name prefix to a key. Any error, or no previous run: `rerun=false`,
which is today's behaviour. Always exits 0 (except --set-status: 1 when the status cannot be set). Python 3.8+, standard library only; `gh` is the external tool.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HOLDABLE = ("integration", "e2e-shard")
# Display-name prefix (lower case) -> job key. The names are the `name:` lines of ts/.github/workflows/ci.yml.
NAME_KEYS = (
    ("lint, types", "verify"),
    ("integration tests", "integration"),
    ("web e2e shard", "e2e-shard"),
)
NOT_PASSED = {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}
SKIPPED = {"skipped", None, ""}
DEFAULT_CONFIG = "scripts/delivery/ci-areas.json"
STATUS_CONTEXT = "rerun-first/held"
STATUS_STATES = ("pending", "success", "failure", "error")


class Undecided(Exception):
    """Something prevented a decision; the answer is rerun=false."""


def run(cmd):
    cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Undecided(f"could not run {cmd[0]}: {exc}") from exc
    if proc.returncode != 0:
        raise Undecided(f"{' '.join(cmd[:3])} failed ({proc.returncode}): {(proc.stderr or proc.stdout).strip()[:300]}")
    return proc.stdout.strip()


def gh_api(path, **query):
    cmd = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json", path]
    for key, value in query.items():
        cmd += ["-f", f"{key}={value}"]
    try:
        return json.loads(run(cmd) or "null")
    except json.JSONDecodeError as exc:
        raise Undecided(f"gh api {path} returned invalid JSON: {exc}") from exc


def post_status(repo, sha, state, description, target_url=""):
    """Set the `rerun-first/held` commit status on `sha` with the workflow's token. Raises Undecided."""
    if state not in STATUS_STATES:
        raise Undecided(f"bad status state {state!r}")
    if not (repo and sha):
        raise Undecided("missing --repo or --sha for the status")
    cmd = ["gh", "api", "--method", "POST", "-H", "Accept: application/vnd.github+json",
           f"repos/{repo}/statuses/{sha}", "-f", f"state={state}", "-f", f"context={STATUS_CONTEXT}",
           "-f", f"description={' '.join(description.split())[:140]}"]
    if target_url:
        cmd += ["-f", f"target_url={target_url}"]
    run(cmd)


def job_key(name):
    """A job's display name -> its key; a matrix leg collapses to its base job."""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", name or "").strip().lower()
    for prefix, key in NAME_KEYS:
        if base.startswith(prefix):
            return key
    return base


def opted_in(config_path):
    try:
        with open(config_path, encoding="utf-8") as fh:
            return json.load(fh).get("rerun_first") is True
    except (OSError, ValueError, AttributeError):
        return False


def not_passed(jobs, selected):
    """Job keys that did not pass: failed-like, or skipped/absent while selected. `selected` None = all HOLDABLE+verify."""
    by_name = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        by_name.setdefault(job_key(job.get("name")), []).append(job.get("conclusion"))
    out = []
    for key in sorted(set(by_name) | set(HOLDABLE)):
        concl = by_name.get(key, [None])
        if any(c in NOT_PASSED for c in concl):
            out.append(key)
        elif key in HOLDABLE and (selected is None or key in selected) and \
                (not any(c == "success" for c in concl)):
            out.append(key)
    return [k for k in out if k in HOLDABLE or k in by_name]


def previous_jobs(repo, workflow, branch, sha, event):
    """(previous head sha, its latest completed run's jobs), or Undecided."""
    runs = gh_api(f"repos/{repo}/actions/workflows/{workflow}/runs", branch=branch, event=event,
                  status="completed", per_page="30")
    items = [r for r in (runs.get("workflow_runs", []) if isinstance(runs, dict) else [])
             if isinstance(r, dict) and r.get("head_sha") and r.get("head_sha") != sha]
    if not items:
        raise Undecided("no previous run of this workflow on the branch")
    items.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    prev = items[0]["head_sha"]
    latest = next(r for r in items if r["head_sha"] == prev)  # newest first
    data = gh_api(f"repos/{repo}/actions/runs/{latest.get('id')}/jobs", per_page="100")
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    if not jobs:
        raise Undecided(f"run {latest.get('id')} has no jobs")
    return prev, latest.get("id"), jobs


def decide(args):
    if args.only:
        first = [k for k in args.only.split(",") if k]
        held = [k for k in HOLDABLE if k not in first]
        return False, first, held, "second run: the jobs held back by the first run (rerun stays false: no third run)"
    if not opted_in(args.config):
        return False, [], [], f"rerun_first is not true in {args.config}"
    if not (args.repo and args.workflow and args.branch and args.sha):
        raise Undecided("missing --repo, --workflow, --branch or --sha")
    selected = None if args.selected is None else [k for k in args.selected.split(",") if k]
    prev, run_id, jobs = previous_jobs(args.repo, args.workflow, args.branch, args.sha, args.event)
    first = not_passed(jobs, selected)
    if not first:
        return False, [], [], f"every job passed on {prev[:10]} (run {run_id}); nothing to put first"
    held = [k for k in HOLDABLE if k not in first and (selected is None or k in selected)]
    if not held:
        return False, first, [], f"every holdable job is in the first set ({', '.join(first)}); nothing to hold"
    return True, first, held, f"run {run_id} on {prev[:10]}: first {', '.join(first)}; held {', '.join(held)}"


def emit(rerun, first, held, reason, as_json):
    reason = " ".join(reason.split())
    if as_json:
        print(json.dumps({"rerun": rerun, "first": first, "held": ",".join(held), "reason": reason}))
        return
    text = f"rerun={'true' if rerun else 'false'}\nfirst={json.dumps(first)}\nheld={','.join(held) if rerun or held else ''}\nreason={reason}\n"
    print("ci_rerun_first: " + text.replace("\n", " ").strip())
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        try:
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"ci_rerun_first: could not write {target}: {exc}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--workflow", default="")
    ap.add_argument("--branch", default="")
    ap.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    ap.add_argument("--event", default="pull_request")
    ap.add_argument("--only", default="", help="second run: the jobs to run now; the others stay held")
    ap.add_argument("--selected", default=None, help="comma list of jobs the plan selected")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hold-status", action="store_true",
                    help="when jobs are held, set the pending status first; if that fails, hold nothing")
    ap.add_argument("--set-status", default="", choices=("",) + STATUS_STATES,
                    help="only set the status and exit (success, failure or error from the final job)")
    ap.add_argument("--description", default="")
    ap.add_argument("--target-url", default="")
    args = ap.parse_args(argv)
    if args.set_status:
        try:
            post_status(args.repo, args.sha, args.set_status, args.description or args.set_status, args.target_url)
        except Undecided as exc:
            print(f"ci_rerun_first: could not set the status: {exc}", file=sys.stderr)
            return 1
        print(f"ci_rerun_first: {STATUS_CONTEXT} is {args.set_status} on {args.sha[:10]}")
        return 0
    try:
        rerun, first, held, reason = decide(args)
        if rerun and args.hold_status:
            try:
                post_status(args.repo, args.sha, "pending", "Held jobs not run yet: " + ", ".join(held)
                            + ". A second run does them.", args.target_url)
            except Undecided as exc:
                rerun, first, held = False, [], []
                reason = f"could not set the pending status, so nothing is held: {exc}"
    except Undecided as exc:
        rerun, first, held, reason = False, [], [], f"could not decide, running today's order: {exc}"
    except Exception as exc:  # fail open on anything unexpected
        rerun, first, held, reason = False, [], [], f"unexpected {type(exc).__name__}, running today's order: {exc}"
    emit(rerun, first, held, reason, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
