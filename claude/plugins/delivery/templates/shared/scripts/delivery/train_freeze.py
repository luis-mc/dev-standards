#!/usr/bin/env python3
"""Train freeze (STACKSPEC 13.6): refuse a push to a branch whose ready PR is being tested.

    train_freeze.py --branch NAME [--timeout SECONDS]

Called by the pre-push hook once per pushed branch. A branch is frozen when an open,
non-draft pull request has it as head AND a workflow run for that pull request's head
commit has not completed. Then the push is refused (exit 1) and the pull request and
the run are named. Allowed (exit 0):

  * no open ready pull request for the branch (none, a draft, or one closed unmerged:
    the train was abandoned),
  * every run of the head commit has completed, passed or failed (fix forward works),
  * GitHub cannot be reached, `gh` is missing or answers with an error: the push goes
    through with a warning, because the ready PR's CI still decides the merge (D4),
  * DELIVERY_FREEZE_OVERRIDE=1 is set: the push goes through and the output says the
    running CI will restart (D9).

A late branch (one that was not green when the ready PR opened) is not pushed into the
train; it rides the next one.

At most two `gh` calls, each with a short timeout: `gh pr list --head NAME`, and only
when a ready PR exists, `gh run list --commit SHA`.
Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

DEFAULT_TIMEOUT = 8.0


class GhError(Exception):
    pass


def gh_json(args: list[str], timeout: float) -> object:
    gh = shutil.which("gh")
    if gh is None:
        raise GhError("the GitHub CLI (gh) is not installed")
    try:
        proc = subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise GhError("gh did not answer within %g s" % timeout) from None
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhError("could not run gh: %s" % exc) from exc
    if proc.returncode != 0:
        raise GhError(((proc.stderr or proc.stdout).strip().splitlines() or ["gh failed"])[0][:200])
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GhError("gh returned invalid JSON: %s" % exc) from exc


def find_freeze(branch: str, timeout: float) -> dict | None:
    """The ready PR and its running runs when `branch` is frozen, else None.
    Raises GhError when GitHub cannot say."""
    prs = gh_json(["pr", "list", "--head", branch, "--state", "open", "--limit", "20",
                   "--json", "number,isDraft,url,headRefOid"], timeout)
    if not isinstance(prs, list):
        raise GhError("gh pr list did not return a list")
    ready = [p for p in prs if isinstance(p, dict) and not p.get("isDraft")]
    if not ready:
        return None
    pr = ready[0]
    sha = str(pr.get("headRefOid") or "")
    if not sha:
        raise GhError("gh pr list gave no head commit for PR #%s" % pr.get("number"))
    runs = gh_json(["run", "list", "--commit", sha, "--limit", "50",
                    "--json", "databaseId,workflowName,status,conclusion"], timeout)
    if not isinstance(runs, list):
        raise GhError("gh run list did not return a list")
    running = [r for r in runs if isinstance(r, dict) and r.get("status") != "completed"]
    if not running:
        return None
    return {"pr": pr, "sha": sha, "running": running}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--branch", required=True, help="the branch being pushed")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help="seconds one gh call may take (default %g)" % DEFAULT_TIMEOUT)
    args = ap.parse_args(argv)
    try:
        frozen = find_freeze(args.branch, args.timeout)
    except GhError as exc:
        print("pre-push: warning: could not check whether %s is frozen (%s); allowing the push. "
              "The ready PR's CI still decides the merge." % (args.branch, exc), file=sys.stderr)
        return 0
    if frozen is None:
        return 0
    pr, run = frozen["pr"], frozen["running"][0]
    what = "PR #%s (%s): CI is running on %s, run %s (%s, %s)" % (
        pr.get("number"), pr.get("url"), frozen["sha"][:10], run.get("databaseId"),
        run.get("workflowName"), run.get("status"))
    if os.environ.get("DELIVERY_FREEZE_OVERRIDE") == "1":
        print("pre-push: DELIVERY_FREEZE_OVERRIDE=1: pushing to the frozen branch %s anyway. %s. "
              "The running CI will restart on the new head." % (args.branch, what), file=sys.stderr)
        return 0
    print("pre-push: blocked. %s is frozen: %s." % (args.branch, what), file=sys.stderr)
    print("  Wait for the run (python scripts/delivery/ci_watch.py %s); once it finishes, passed or\n"
          "  failed, pushing is allowed and a fix goes forward. A branch that is late rides the next\n"
          "  train. To push now and restart that CI on purpose: DELIVERY_FREEZE_OVERRIDE=1 git push"
          % frozen["sha"][:10], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
