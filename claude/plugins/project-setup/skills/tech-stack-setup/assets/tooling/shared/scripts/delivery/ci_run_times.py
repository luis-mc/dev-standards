#!/usr/bin/env python3
"""Write how long this CI run took: the `ci-run-times` artifact (DELIVERYSPEC DL-82; DS26).

The last job of the CI workflow runs this script. It reads the run's jobs from the GitHub API, writes
`ci-run-times.json` (wall time, scope, each job's queue and run time, longest first) and a job summary, and the
workflow uploads the file under the stable artifact name `ci-run-times` (artifact_prune.py keeps the newest, a
progress page reads it). The target (`--target-minutes`, default 15) is report-only: the script never fails the
run; a missing token or an API error writes a note and exits 0.

    ci_run_times.py [--target-minutes N] [--out FILE]

Environment (set by GitHub Actions): GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT,
GITHUB_STEP_SUMMARY; CI_SCOPE (optional, the ci_scope.py result to show). Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

ARTIFACT_NAME = "ci-run-times"


def parse(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def seconds(start: str | None, end: str | None) -> int | None:
    a, b = parse(start), parse(end)
    return None if a is None or b is None else max(0, round(b - a))


def summarize(run: dict, jobs: list[dict], now: datetime, scope: str = "", target_seconds: int = 900) -> dict:
    """Wall time runs from the run's start to `now` (this job is the last). Jobs that never ran (skipped, this
    one) are left out. Longest first."""
    times = []
    for j in jobs:
        ran = seconds(j.get("started_at"), j.get("completed_at"))
        if ran is None or j.get("conclusion") == "skipped":
            continue
        times.append({"name": j.get("name", ""), "conclusion": j.get("conclusion") or j.get("status", ""),
                      "queuedSeconds": seconds(j.get("created_at"), j.get("started_at")) or 0, "seconds": ran})
    times.sort(key=lambda t: (-t["seconds"], t["name"]))
    wall = seconds(run.get("run_started_at") or run.get("created_at"), now.isoformat()) or 0
    return {"event": run.get("event", ""), "headSha": run.get("head_sha", ""), "scope": scope, "wallSeconds": wall,
            "targetSeconds": target_seconds, "overTarget": wall > target_seconds, "jobs": times}


def minutes(s: int) -> str:
    return f"{s // 60}:{s % 60:02d}"


def to_markdown(t: dict) -> str:
    verdict = "over" if t["overTarget"] else "within"
    rows = [f"| {j['name']} | {j['conclusion']} | {minutes(j['queuedSeconds'])} | {minutes(j['seconds'])} |"
            for j in t["jobs"]]
    return "\n".join([
        f"## CI run time: {minutes(t['wallSeconds'])} ({verdict} the {minutes(t['targetSeconds'])} target, report only)",
        "", f"Scope: {t['scope'] or 'unknown'} · event: {t['event']} · head {t['headSha'][:8]}", "",
        "| Job | Result | Queued | Ran |", "| --- | --- | ---: | ---: |", *rows])


def get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"authorization": f"Bearer {token}",
                                               "accept": "application/vnd.github+json",
                                               "x-github-api-version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target-minutes", type=int, default=15)
    p.add_argument("--out", default="ci-run-times.json")
    a = p.parse_args(argv)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")

    def note(text: str) -> None:
        print(text)
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")

    try:
        token, repo, run_id = (os.environ.get(k) for k in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
        if not token or not repo or not run_id:
            raise ValueError("no token, repository or run id")
        api = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/attempts/{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
        run = get(api, token)
        jobs = get(f"{api}/jobs?per_page=100", token).get("jobs", [])
        times = summarize(run, jobs, datetime.now(timezone.utc), os.environ.get("CI_SCOPE", ""), a.target_minutes * 60)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(times, indent=2) + "\n")
        note(to_markdown(times))
    except Exception as e:  # report only: a failure to measure never fails the run
        note(f"CI run time not written: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
