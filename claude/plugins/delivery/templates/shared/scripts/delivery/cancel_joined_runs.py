#!/usr/bin/env python3
"""Cancel the CI runs of agent branches that an integration branch already contains.

    cancel_joined_runs.py --into <INTEGRATION> [--remote origin] [--repo OWNER/NAME] [--yes]

After the orchestrator joins agent branches into `<ID>-integration`, the runs those
branches started are not needed, but on a single self-hosted runner they keep it
busy and the release pull request's CI waits. This script finds them and cancels them.

A run is cancelled only when all of these hold:
  - its status is queued, waiting, requested, pending or in_progress;
  - its head branch is merged into <remote>/<INTEGRATION> (`git branch -r --merged`);
  - that branch is not the integration branch and not the default branch;
  - its head commit is reachable from <remote>/<INTEGRATION>, so a branch pushed
    again after the join is left alone.
Runs of any other branch are never touched.

It is a dry run by default: it prints the plan and cancels nothing. With --yes it runs
`gh run cancel <id>` for each run and prints each result.

Output, one line per run: `cancel <id> <branch> <workflow> <url>` in the plan, then
with --yes `cancelled <id>` or `failed <id>: <reason>`. A last line gives the counts.

Exit: 0 done (also when nothing matches, or a dry run), 1 a cancel failed,
2 usage error, no repository, or gh missing.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

ACTIVE = {"queued", "waiting", "requested", "pending", "in_progress"}
CREATE_NO_WINDOW = 0x08000000


def run(cmd: list[str]) -> tuple[int, str, str]:
    """The one subprocess seam: tests replace it. Returns (code, stdout, stderr)."""
    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = CREATE_NO_WINDOW
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    return p.returncode, p.stdout, p.stderr


def git(*args: str) -> tuple[int, str, str]:
    return run(["git", *args])


def gh(*args: str, repo: str | None = None) -> tuple[int, str, str]:
    return run(["gh", *args] + (["--repo", repo] if repo else []))


def default_branch(remote: str) -> str:
    code, out, _ = git("symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
    if code == 0 and out.strip():
        return out.strip().removeprefix(f"{remote}/")
    for name in ("main", "master"):
        if git("rev-parse", "--verify", "-q", f"refs/remotes/{remote}/{name}")[0] == 0:
            return name
    return "main"


def merged_branches(remote: str, into: str) -> list[str]:
    code, out, err = git("branch", "-r", "--merged", f"{remote}/{into}")
    if code != 0:
        raise RuntimeError(err.strip() or f"git branch --merged failed for {remote}/{into}")
    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line or " -> " in line or not line.startswith(remote + "/"):
            continue
        names.append(line[len(remote) + 1:])
    skip = {into, default_branch(remote)}
    return [n for n in names if n not in skip and n != "HEAD"]


def plan(remote: str, into: str, repo: str | None) -> list[dict]:
    merged = set(merged_branches(remote, into))
    code, out, err = gh("run", "list", "--json", "databaseId,headBranch,headSha,status,workflowName,url",
                        "--limit", "200", repo=repo)
    if code != 0:
        raise RuntimeError(err.strip() or "gh run list failed")
    runs = json.loads(out or "[]")
    picked = []
    for r in runs:
        if r.get("status") not in ACTIVE or r.get("headBranch") not in merged:
            continue
        sha = r.get("headSha") or ""
        if not sha or git("merge-base", "--is-ancestor", sha, f"{remote}/{into}")[0] != 0:
            continue
        picked.append(r)
    return picked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cancel_joined_runs.py", description=__doc__.split("\n")[0])
    ap.add_argument("--into", required=True, help="integration branch name")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--repo", help="OWNER/NAME passed to gh")
    ap.add_argument("--yes", action="store_true", help="cancel the runs (default: dry run)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if git("rev-parse", "--verify", "-q", f"refs/remotes/{a.remote}/{a.into}")[0] != 0:
        print(f"cancel_joined_runs: no branch {a.remote}/{a.into}", file=sys.stderr)
        return 2
    if gh("--version")[0] != 0:
        print("cancel_joined_runs: gh is missing or not working", file=sys.stderr)
        return 2
    try:
        runs = plan(a.remote, a.into, a.repo)
    except (RuntimeError, ValueError) as e:
        print(f"cancel_joined_runs: {e}", file=sys.stderr)
        return 2
    for r in runs:
        print(f"cancel {r['databaseId']} {r['headBranch']} {r.get('workflowName', '')} {r.get('url', '')}".rstrip())
    if not a.yes:
        print(f"dry run: {len(runs)} run(s) would be cancelled; pass --yes to cancel")
        return 0
    failed = 0
    for r in runs:
        code, _, err = gh("run", "cancel", str(r["databaseId"]), repo=a.repo)
        if code == 0:
            print(f"cancelled {r['databaseId']}")
        else:
            failed += 1
            print(f"failed {r['databaseId']}: {err.strip() or 'gh run cancel failed'}")
    print(f"{len(runs) - failed} cancelled, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
