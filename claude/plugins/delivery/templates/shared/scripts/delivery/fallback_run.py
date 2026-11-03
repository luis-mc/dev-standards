#!/usr/bin/env python3
"""Run ONE shard as the fallback: claim last, then test, then post (Option 4, CIR10 S8).

    fallback_run.py --sha SHA --shard ID --who cloud|hosted [--timeout-min N] [--root DIR] [--remote origin]

The launcher (`fallback_launch.py`) starts a cloud session or a hosted job that runs this after checkout and
setup. Order, from section 4.3 of the CIR10 proposal:
  1. HEAD must be SHA (the job checks it out; a different HEAD is an error, never a pass).
  2. Take the claim for (SHA, shard). If the main runner already holds it, end now: no tests, no status.
     The claim is the LAST step before the first test command, so a slow boot loses cleanly.
  3. Run the shard with `cloud_shard.py` (result JSON, result branch).
  4. Post ONE commit status for the shard's context, only as the claim holder.

The claim and the claim-checked poster come from the Option 4 core (`ci_claim.py`, DL23). If that module is
missing the run fails closed: it claims nothing, runs nothing, posts nothing, and exits 2.
Exit 0 ran and posted (or lost the claim), 1 the shard failed (the failure is posted), 2 error.
Standard library only.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cloud_shard  # noqa: E402
import cloud_status  # noqa: E402


def head_sha(root: str) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return r.stdout.strip().lower()


def load_claim():
    """The Option 4 core: take(root, remote, sha, shard, who) -> bool; optional post_status(...)."""
    try:
        import ci_claim  # noqa: PLC0415
        return ci_claim
    except ImportError:
        return None


def main(argv=None, claim=None, shard_runner=None) -> int:
    ap = argparse.ArgumentParser(prog="fallback_run.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--sha", required=True)
    ap.add_argument("--shard", required=True)
    ap.add_argument("--who", choices=["cloud", "hosted"], required=True)
    ap.add_argument("--timeout-min", type=float, default=None)
    ap.add_argument("--root", default=".")
    ap.add_argument("--remote", default="origin")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    sha = args.sha.lower()
    if head_sha(root) != sha:
        print("fallback_run: HEAD is not %s: refusing to run" % sha[:10], file=sys.stderr)
        return 2
    claim = claim or load_claim()
    if claim is None:
        print("fallback_run: the claim module (ci_claim.py) is missing: nothing is run", file=sys.stderr)
        return 2
    if not claim.take(root, args.remote, sha, args.shard, args.who):
        print("fallback_run: shard %s of %s is already claimed: ending, no tests, no status" % (args.shard, sha[:10]))
        return 0
    cfg = cloud_status.cloud_settings(cloud_status.read_config(root))
    table = cloud_shard.load_table(os.path.join(root, *cfg["table"].split("/")))
    result = (shard_runner or cloud_shard.run_shard)(table, args.shard, root, sha, args.timeout_min)
    cloud_shard.write_result(result, os.path.join(root, ".delivery", "ci-results", result["sha"], args.shard + ".json"))
    ok, msg = cloud_shard.push_result(result, root, cfg["prefix"], args.remote)
    print("fallback_run: %s %s: %s" % (args.shard, result["state"], result["summary"]))
    if not ok:
        print("fallback_run: result branch not pushed: %s" % msg, file=sys.stderr)
    repo = cfg["repo"] or os.environ.get("GITHUB_REPOSITORY", "")
    token_env = cfg["token_env"] or ("GITHUB_TOKEN" if args.who == "hosted" else "")
    try:
        post = getattr(claim, "post_status", None)
        if post is not None:
            post(root, args.remote, result, repo, token_env)
        else:  # we hold the claim, so posting here is the one post
            sha_, body = cloud_status.status_payload(result, sha)
            cloud_status.post_status(repo, sha_, body, cloud_status.token_from(token_env))
    except Exception as exc:  # noqa: BLE001
        print("fallback_run: status not posted: %s" % exc, file=sys.stderr)
        return 2
    return {"success": 0, "failure": 1}.get(result["state"], 2)


if __name__ == "__main__":
    sys.exit(main())
