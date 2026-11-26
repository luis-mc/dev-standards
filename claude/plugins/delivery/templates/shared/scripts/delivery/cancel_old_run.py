#!/usr/bin/env python3
"""Cancel the in-progress CI runs of a pull request's head, so a fix push can go (DL424).

    cancel_old_run.py --pr N [--repo OWNER/NAME] [--dry-run]

The train freeze (train_freeze.py) refuses a push to the head branch of a ready pull request
while a run of its head commit has not finished. After `gh run rerun --failed` that can be a long
wait for a run the fix makes useless. This script finds the pull request's head commit, runs
`gh run cancel` on every run of that commit that has not completed, records each cancelled run
in .delivery/cancelled-runs.json of the main checkout (the freeze lets those runs pass, also
while GitHub still shows them ending) and writes a `cancelled` CI event to the delivery ledger
(best effort). Runs of other commits or branches are never touched. --dry-run prints the plan only.

Output, one line per run: `cancel <id> <workflow> <status>` in the plan, then `cancelled <id>`
or `failed <id>: <reason>`. Exit: 0 done (also when no run is active), 1 a cancel failed,
2 usage or GitHub error.
Python 3.11+, standard library only; `gh` is the one external tool.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import delivery_common as dc  # noqa: E402


def gh(*args: str, repo: str | None = None) -> tuple[int, str, str]:
    """The one subprocess seam: tests replace it. DELIVERY_GH names the gh program (default `gh`)."""
    cmd = [os.environ.get("DELIVERY_GH") or "gh", *args] + (["--repo", repo] if repo else [])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)
    return p.returncode, p.stdout, p.stderr


def remember(root, run_ids: list[str]) -> None:
    """Add the run ids to .delivery/cancelled-runs.json (a JSON object: id -> time)."""
    path = root / dc.CANCELLED_RUNS_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for rid in run_ids:
        data[str(rid)] = now
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cancel_old_run.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", required=True, type=int, help="the pull request number")
    ap.add_argument("--repo", help="OWNER/NAME (default: the repository of this checkout)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, cancel nothing")
    a = ap.parse_args(argv)

    code, out, err = gh("pr", "view", str(a.pr), "--json", "headRefOid,headRefName", repo=a.repo)
    if code != 0:
        print("cancel_old_run: gh pr view failed: %s" % (err.strip() or out.strip() or "no answer"), file=sys.stderr)
        return 2
    try:
        pr = json.loads(out)
        sha, branch = str(pr["headRefOid"]), str(pr.get("headRefName") or "")
    except (ValueError, KeyError, TypeError):
        print("cancel_old_run: gh pr view gave no head commit for PR #%s" % a.pr, file=sys.stderr)
        return 2
    code, out, err = gh("run", "list", "--commit", sha, "--limit", "50",
                        "--json", "databaseId,workflowName,status", repo=a.repo)
    if code != 0:
        print("cancel_old_run: gh run list failed: %s" % (err.strip() or "no answer"), file=sys.stderr)
        return 2
    try:
        runs = [r for r in json.loads(out) if isinstance(r, dict) and r.get("status") != "completed"]
    except (ValueError, TypeError):
        print("cancel_old_run: gh run list returned invalid JSON", file=sys.stderr)
        return 2
    if not runs:
        print("cancel_old_run: PR #%s head %s has no active run; nothing to cancel" % (a.pr, sha[:10]))
        return 0
    for r in runs:
        print("cancel %s %s %s" % (r.get("databaseId"), r.get("workflowName", ""), r.get("status")))
    if a.dry_run:
        print("dry run: %d run(s) would be cancelled" % len(runs))
        return 0

    done, failed = [], 0
    for r in runs:
        rid = str(r.get("databaseId"))
        c, _, e = gh("run", "cancel", rid, repo=a.repo)
        if c == 0:
            print("cancelled %s" % rid)
            done.append(rid)
        else:
            failed += 1
            print("failed %s: %s" % (rid, e.strip() or "gh run cancel failed"))
    if done:
        root = dc.main_checkout_root()
        try:
            remember(root, done)
        except OSError as exc:
            print("cancel_old_run: warning: could not write %s (%s)" % (dc.CANCELLED_RUNS_PATH, exc), file=sys.stderr)
        dc.ledger_record(root, "ci", sha=sha, state="cancelled", branch=branch or None, pr=a.pr,
                         by="cancel_old_run.py")
        print("the train freeze now lets a fix push to %s through" % (branch or "the branch"))
    print("%d cancelled, %d failed" % (len(done), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
