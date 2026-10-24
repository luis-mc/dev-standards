#!/usr/bin/env python3
"""Wait for the CI workflow runs of one commit and report how they ended.

STACKSPEC 13.6: CI is watched through the workflow runs for the head commit,
never through a pull request's check list, which can be read before the new run
is listed (an empty or stale list then looks like a pass). This script lists
runs with `gh run list --commit SHA` and decides only when

  * at least one run of the named workflow exists for the commit, and
  * every run of that workflow for the commit is completed.

Skipped runs (CO400): a run that executed no job (conclusion skipped, or a push run
whose jobs were all skipped, "already tested on the pull request") is not a pass when
the commit is the head of an open pull request: the watch then waits for a run that
executed jobs (the pull_request run) and is green only when every run that executed
succeeded and at least one did. A commit with no open pull request keeps the old rule
(skipped counts as success). The open pull request is read with
`gh api repos/{owner}/{repo}/commits/SHA/pulls`, never from a PR check list.

Exit codes (shared by the delivery scripts): 0 every run succeeded or was
skipped (see above), 1 any other conclusion (the failed jobs are printed), 2 usage
error or `gh` missing or unusable, 4 timed out ("no real run yet" when only skipped
runs exist for a pull request head). It never exits 0 when it could not decide.

Runner health (DL7, warnings only): while it waits, a job that has been queued for
more than 10 minutes (--queue-warn-seconds) is reported once, when no online runner
carries its labels, or, when the runners cannot be listed (that needs admin rights),
as "queued 10+ min". It never changes the exit code. GitHub-hosted labels are not
checked: a queued hosted job is the platform's wait, not a missing runner.

Slowest job (TC8, information only): once every run is complete, one summary lists each run's
wall time (first job start to last job end), its slowest job with that job's share of the
run, and the job's two slowest steps, from `gh run view --json jobs`. It never changes the
exit code and prints nothing extra when anything cannot be read.

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
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script dir off sys.path
import runner_health  # noqa: E402

OK_CONCLUSIONS = {"success", "skipped"}
LIST_FIELDS = "databaseId,workflowName,status,conclusion,event,headSha"
MAX_CONSECUTIVE_GH_ERRORS = 5
QUEUE_WARN_SECONDS = 600


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


def executed_jobs(run: dict, repo: str | None) -> bool:
    """True when a completed, non-failed run ran at least one job.

    A `skipped` conclusion ran nothing; a `success` push run may still have only skipped
    jobs. Jobs are read only for push runs, the shape of the "already tested on the pull
    request" skip; any other successful run counts as executed."""
    if run.get("conclusion") == "skipped":
        return False
    if run.get("conclusion") != "success" or run.get("event") != "push":
        return True
    data = gh_json(["run", "view", str(run.get("databaseId")), "--json", "jobs", *repo_args(repo)])
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    return not jobs or any(j.get("conclusion") != "skipped" for j in jobs if isinstance(j, dict))


def has_open_pr(sha: str, repo: str | None) -> bool:
    """True when `sha` is the head commit of an open pull request."""
    base = f"repos/{repo}" if repo else "repos/{owner}/{repo}"
    data = gh_json(["api", f"{base}/commits/{sha}/pulls"])
    if not isinstance(data, list):
        raise GhError("gh api commits/SHA/pulls did not return a list")
    return any(isinstance(p, dict) and p.get("state") == "open"
               and str((p.get("head") or {}).get("sha", sha)).startswith(sha[:7])
               for p in data)


def queued_age(job: dict, now: float) -> float | None:
    """Seconds a job has been queued, from its created_at; None when unknown."""
    raw = job.get("created_at")
    if not isinstance(raw, str):
        return None
    try:
        return now - datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def warn_queued_jobs(pending: list[dict], repo: str | None, warned: set, threshold: float,
                     now: float | None = None) -> None:
    """Warn once per job queued over `threshold` seconds with no online runner for its
    labels (or, when runners cannot be listed, say it has been queued that long)."""
    now = time.time() if now is None else now
    runners: list | None | str = "unlisted"
    why = ""
    for run in pending:
        base = f"repos/{repo}" if repo else "repos/{owner}/{repo}"
        try:
            data = gh_json(["api", f"{base}/actions/runs/{run.get('databaseId')}/jobs?per_page=100"])
        except GhError:
            continue
        for job in (data.get("jobs", []) if isinstance(data, dict) else []):
            jid = job.get("id")
            if job.get("status") != "queued" or jid in warned:
                continue
            age = queued_age(job, now)
            if age is None or age < threshold:
                continue
            labels = [str(x) for x in job.get("labels") or []]
            if labels and runner_health.is_hosted(labels):
                continue
            if runners == "unlisted":
                runners, why = runner_health.list_online_runners(repo)
            minutes = int(age // 60)
            name = f"{run.get('workflowName')} / {job.get('name')}"
            if runners is None:
                print(f"ci_watch: WARNING: job {name} has been queued 10+ min ({minutes} min); "
                      f"the online runners could not be listed ({why})", flush=True)
            elif labels and not any(runner_health.runner_carries(r, labels) for r in runners):
                print(f"ci_watch: WARNING: job {name} has been queued {minutes} min and no online "
                      f"runner carries its labels [{', '.join(labels)}]", flush=True)
            else:
                continue  # a runner exists; the job is waiting its turn
            warned.add(jid)


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


def parse_time(raw: object) -> float | None:
    if not isinstance(raw, str) or raw.startswith("0001"):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def span(item: dict) -> float | None:
    start, end = parse_time(item.get("startedAt")), parse_time(item.get("completedAt"))
    return end - start if start is not None and end is not None and end >= start else None


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60}m{seconds % 60:02d}s"


def summary_lines(run: dict, jobs: list) -> list[str]:
    """The summary of one run: wall time, slowest job and its share, two slowest steps."""
    timed = [(span(j), j) for j in jobs if isinstance(j, dict)]
    timed = [(d, j) for d, j in timed if d is not None]
    starts = [parse_time(j.get("startedAt")) for _, j in timed]
    ends = [parse_time(j.get("completedAt")) for _, j in timed]
    if not timed or None in starts or None in ends:
        return []
    wall = max(ends) - min(starts)
    dur, job = max(timed, key=lambda t: t[0])
    share = f"{round(100 * dur / wall)}% of the run" if wall > 0 else "the whole run"
    lines = [f"  run {run.get('databaseId')} ({run.get('workflowName')}): wall {fmt_duration(wall)}, "
             f"slowest job {job.get('name')} {fmt_duration(dur)} ({share})"]
    steps = [(span(s), s) for s in job.get("steps", []) or [] if isinstance(s, dict)]
    steps = sorted(((d, s) for d, s in steps if d is not None), key=lambda t: -t[0])[:2]
    if steps:
        lines.append("    slowest steps: " + "; ".join(
            f"{s.get('name')} {fmt_duration(d)}" for d, s in steps))
    return lines


def record_suite_times(run: dict, jobs: list) -> None:
    """STACKSPEC 13.8: store the CI time of each declared suite (suites.json ci_step) for run_suite.py's guard."""
    try:
        import run_suite
        run_suite.record_ci_times(run_suite.repo_root(), run, jobs)
    except Exception:  # noqa: BLE001 - recording must never break the watch
        return


def print_slowest_job_summary(runs: list[dict], repo: str | None) -> None:
    """Information only: any error, anywhere, prints nothing and changes nothing."""
    try:
        out: list[str] = []
        for run in runs:
            data = gh_json(["run", "view", str(run.get("databaseId")), "--json", "jobs",
                            *repo_args(repo)])
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            record_suite_times(run, jobs)
            out += summary_lines(run, jobs)
        if out:
            print("ci_watch: slowest job per run")
            print(chr(10).join(out))
    except Exception:  # noqa: BLE001 - a summary must never break the watch
        return


def ledger_ci(sha: str, state: str) -> None:
    """Best effort: record the decision in the delivery ledger (no-op without the plugin)."""
    try:
        import delivery_common as dc
        dc.ledger_record(dc.repo_root(), "ci", sha=sha, state=state, by="ci_watch.py")
    except Exception:  # noqa: BLE001
        return


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
    ap.add_argument("--queue-warn-seconds", type=float, default=QUEUE_WARN_SECONDS,
                    help="warn about a job queued this long with no runner for its labels "
                         "(default 600)")
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
    warned: set = set()
    while True:
        state = ""
        decided = False
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
                warn_queued_jobs(pending, args.repo, warned, args.queue_warn_seconds)
            else:
                bad = [r for r in runs if r.get("conclusion") not in OK_CONCLUSIONS]
                decided = True
                try:
                    idle = [r for r in runs if r not in bad and not executed_jobs(r, args.repo)]
                    # Skipped runs only matter when the head belongs to an open PR.
                    if idle and not bad and len(idle) == len(runs) and has_open_pr(sha, args.repo):
                        state = (f"no real run yet for {sha[:10]}: only skipped {args.workflow} "
                                 f"run(s) so far, waiting for the pull_request run")
                        decided = False
                except GhError as exc:
                    errors += 1
                    state = f"gh error ({errors}): {exc}"
                    if errors >= MAX_CONSECUTIVE_GH_ERRORS:
                        print(f"ci_watch: giving up, gh failed {errors} times in a row: {exc}",
                              file=sys.stderr)
                        return 2
                    decided = False
            if decided:
                if not bad:
                    print(f"ci_watch: {len(runs)} {args.workflow} run(s) for {sha[:10]} "
                          "succeeded")
                    print_slowest_job_summary(runs, args.repo)
                    ledger_ci(sha, "success")
                    return 0
                print(f"ci_watch: {len(bad)} of {len(runs)} {args.workflow} run(s) for "
                      f"{sha[:10]} did not succeed")
                for run in bad:
                    print_failed_jobs(run, args.repo)
                print_slowest_job_summary(runs, args.repo)
                ledger_ci(sha, "failure")
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
