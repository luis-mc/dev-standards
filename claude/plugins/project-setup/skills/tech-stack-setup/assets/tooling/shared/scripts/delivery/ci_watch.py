#!/usr/bin/env python3
"""Wait for the CI workflow runs of one commit and report how they ended.

STACKSPEC 13.6: CI is watched through the workflow runs for the head commit,
never through a pull request's check list, which can be read before the new run
is listed (an empty or stale list then looks like a pass). This script lists
runs with `gh run list --commit SHA` and decides only when

  * at least one run of the named workflow exists for the commit, and
  * every run of that workflow for the commit is completed.

Exit codes (shared by the delivery scripts): 0 every run succeeded or was
skipped, 1 any other conclusion (the failed jobs are printed), 2 usage error or
`gh` missing or unusable, 4 timed out. It never exits 0 when it could not decide.

Python 3.11+, standard library only; `gh` is the one external tool.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time

OK_CONCLUSIONS = {"success", "skipped"}
LIST_FIELDS = "databaseId,workflowName,status,conclusion,event,headSha"
MAX_CONSECUTIVE_GH_ERRORS = 5


class GhError(Exception):
    pass


def gh_json(args: list[str]) -> object:
    """Run `gh` with an argument list and parse its JSON output."""
    # The resolved path, so Windows finds gh whatever its extension.
    gh = shutil.which("gh") or "gh"
    try:
        proc = subprocess.run(
            [gh, *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhError(f"could not run gh: {exc}") from exc
    if proc.returncode != 0:
        raise GhError(f"gh {' '.join(args[:2])} failed ({proc.returncode}): "
                      f"{(proc.stderr or proc.stdout).strip()[:300]}")
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GhError(f"gh {' '.join(args[:2])} returned invalid JSON: {exc}") from exc


def repo_args(repo: str | None) -> list[str]:
    return ["--repo", repo] if repo else []


def list_runs(sha: str, workflow: str, repo: str | None) -> list[dict]:
    data = gh_json(["run", "list", "--commit", sha, "--workflow", workflow,
                    "--limit", "100", "--json", LIST_FIELDS, *repo_args(repo)])
    if not isinstance(data, list):
        raise GhError("gh run list did not return a list")
    # `--commit` already filters; this guards against a stale or wrong answer.
    return [r for r in data
            if isinstance(r, dict)
            and str(r.get("headSha", sha)).startswith(sha[:7])]


def print_failed_jobs(run: dict, repo: str | None) -> None:
    rid = run.get("databaseId")
    print(f"  run {rid} ({run.get('workflowName')}, {run.get('event')}): "
          f"{run.get('conclusion') or 'no conclusion'}")
    try:
        data = gh_json(["run", "view", str(rid), "--json", "jobs", *repo_args(repo)])
    except GhError as exc:
        print(f"    could not read the jobs: {exc}")
        return
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    bad = [j for j in jobs if j.get("conclusion") not in OK_CONCLUSIONS]
    if not bad:
        print("    no failed job reported")
    for job in bad:
        print(f"    FAILED job: {job.get('name')} ({job.get('conclusion') or job.get('status')})")
        for step in job.get("steps", []) or []:
            if step.get("conclusion") not in OK_CONCLUSIONS | {None, ""}:
                print(f"      step: {step.get('name')} ({step.get('conclusion')})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Wait for the CI workflow runs of a commit (never reads PR checks).")
    ap.add_argument("sha", help="commit sha whose runs to watch")
    ap.add_argument("--workflow", default="ci.yml",
                    help="workflow file name or name (default ci.yml)")
    ap.add_argument("--timeout", type=float, default=3600,
                    help="seconds to wait before giving up with exit 4 (default 3600)")
    ap.add_argument("--interval", type=float, default=30,
                    help="seconds between polls (default 30)")
    ap.add_argument("--repo", help="OWNER/NAME (default: the current repository)")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.sha):
        print(f"ci_watch: {args.sha!r} is not a commit sha", file=sys.stderr)
        return 2
    if args.timeout <= 0 or args.interval < 0:
        print("ci_watch: --timeout must be positive and --interval not negative",
              file=sys.stderr)
        return 2
    if shutil.which("gh") is None:
        print("ci_watch: the GitHub CLI (gh) is not installed or not on PATH",
              file=sys.stderr)
        return 2

    sha = args.sha.lower()
    deadline = time.monotonic() + args.timeout
    errors = 0
    last_state = ""
    while True:
        state = ""
        try:
            runs = list_runs(sha, args.workflow, args.repo)
            errors = 0
        except GhError as exc:
            errors += 1
            state = f"gh error ({errors}): {exc}"
            if errors >= MAX_CONSECUTIVE_GH_ERRORS:
                print(f"ci_watch: giving up, gh failed {errors} times in a row: {exc}",
                      file=sys.stderr)
                return 2
            runs = None
        if runs is not None:
            pending = [r for r in runs if r.get("status") != "completed"]
            if not runs:
                state = f"no {args.workflow} run for {sha[:10]} yet"
            elif pending:
                state = f"{len(pending)} of {len(runs)} run(s) not completed"
            else:
                bad = [r for r in runs if r.get("conclusion") not in OK_CONCLUSIONS]
                if not bad:
                    print(f"ci_watch: {len(runs)} {args.workflow} run(s) for {sha[:10]} "
                          "succeeded")
                    return 0
                print(f"ci_watch: {len(bad)} of {len(runs)} {args.workflow} run(s) for "
                      f"{sha[:10]} did not succeed")
                for run in bad:
                    print_failed_jobs(run, args.repo)
                return 1
        if state != last_state:
            print(f"ci_watch: waiting, {state}", flush=True)
            last_state = state
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"ci_watch: timed out after {args.timeout:g}s, {state}", file=sys.stderr)
            return 4
        time.sleep(min(args.interval, remaining))


if __name__ == "__main__":
    sys.exit(main())
