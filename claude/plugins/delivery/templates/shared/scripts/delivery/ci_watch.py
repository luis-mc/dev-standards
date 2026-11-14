#!/usr/bin/env python3
"""Wait for the CI workflow runs of one commit and report how they ended.

STACKSPEC 13.6: CI is watched through the workflow runs for the head commit,
never through a pull request's check list, which can be read before the new run
is listed (an empty or stale list then looks like a pass). This script lists
runs with `gh run list --commit SHA` (an abbreviated SHA is first resolved to the full
one, by git or the GitHub API, or the watch exits 2) and decides only when

  * at least one run of the named workflow exists for the commit, and
  * every run of that workflow for the commit is completed.

Skipped runs (DV400): a run that executed no job (conclusion skipped, or a push run
whose jobs were all skipped, "already tested on the pull request") is not a pass when
the commit is the head of an open pull request: the watch then waits for a run that
executed jobs (the pull_request run) and is green only when every run that executed
succeeded and at least one did. A commit with no open pull request keeps the old rule
(skipped counts as success). The open pull request is read with
`gh api repos/{owner}/{repo}/commits/SHA/pulls`, never from a PR check list.

Every workflow (DL139): the watch covers every workflow run for the commit, not only --workflow (that one
must still exist); any failed run exits 1. --only-workflow restores the single-workflow watch.

Ledger (DL132, DL138): the result is written to the main checkout's .delivery/ledger.json even from a git
worktree. The train is matched by branch or PR head; when none exists it is created as `delivery_ledger.py
plan --branch` would, and when no branch can be found the exact plan command is printed.

Exit codes (shared by the delivery scripts): 0 every run succeeded or was
skipped (see above), 1 any other conclusion (the failed jobs are printed), 2 usage
error or `gh` missing or unusable, 4 timed out ("no real run yet" when only skipped
runs exist for a pull request head), 5 gave up: gh failed five times in a row, so the result is
unknown (DL247). It never exits 0 when it could not decide.
A workflow that does not exist in the repository (HTTP 404, "workflow ... not found") is a
usage error, not a transient one: it exits 2 at once, without retrying, and lists the
repository's workflows so the caller can pass the right --workflow. Any other gh error is
retried and gives up with exit 5 after five in a row.

Pinned repository (DL247): at start the watch resolves the repository once (--repo, else
`gh repo view --json nameWithOwner`) and passes it to every later gh call, so it survives its working
directory going away. When the repository cannot be resolved it exits 2 at once.

Runner health (DL7, warnings only): while it waits, a job that has been queued for
more than 10 minutes (--queue-warn-seconds) is reported once, when no online runner
carries its labels, or, when the runners cannot be listed (that needs admin rights),
as "queued 10+ min". It never changes the exit code. GitHub-hosted labels are not
checked: a queued hosted job is the platform's wait, not a missing runner.

Slowest job (TC8, information only): once every run is complete, one summary lists each run's
wall time (first job start to last job end), its slowest job with that job's share of the
run, and the job's two slowest steps, from `gh run view --json jobs`. It never changes the
exit code and prints nothing extra when anything cannot be read.

Fallback (Option 4, CIR10 S8): when `.delivery/config.json` has `ci.fallback` (kind, after_min), every poll with
pending runs measures how long each shard's job has been queued for a runner. A shard over `after_min` minutes
gets one fallback launch (cloud session or hosted runner, `fallback_launch.py`); under it, nothing. A paused cap
prints one warning. It never changes the exit code. This watcher is the session that opened the run; the hourly
routine (`fallback_launch.py sweep`) is only the safety net, so an unattended fallback can start up to an hour
late. --no-fallback turns it off.

Docker trim: when `.delivery/config.json` has `ci.docker_trim: true` (default off) and this PC is Windows with
Docker, the watcher trims Docker Desktop's data disk once after the runs finish, from a throwaway container of
the first image present in `ci.docker_trim_images` (default ["postgres:16"]). A failure only logs a line.
--no-trim skips it.

Post-run hooks (DS30): `.delivery/config.json` may list project commands under
`ci_watch.post_run`, e.g. `{"ci_watch": {"post_run": ["python scripts/delivery/ci_watch_local.py
{run_id} {head}"], "post_run_timeout_seconds": 900}}`. Once every watched run is complete and the
verdict is decided (exit 0 or 1), each hook runs for each run, in list order, from the repository
root. A command is split like a shell would (shlex, no shell is started) and then {run_id},
{head} (the full commit sha), {conclusion} and {workflow} are replaced in each word. A hook that
exits non-zero, times out, cannot start or is malformed is logged to stderr and the next one
runs; hooks never change the exit code and a hook's output is passed through. A project keeps
its machine-only extras (disk trims, extra reports) in its own hook script instead of a fork of
this file. --no-post-run skips them; --config names another config file.

Cancel on red (DL306): while the watched head belongs to a train branch (config `train_branch_re`,
default `^release/`), the first failed job (conclusion failure, timed_out or cancelled) in any run of
that head ends the wait at once. The watcher names the job, runs `gh run cancel` for every run of
that head that is still queued or running (never other commits or branches; never an agent branch),
logs that the push freeze lifts (train_freeze.py reads the live runs, so the freeze ends when they
complete), and exits 1. The runs it cancelled are not a second failure. --no-cancel-on-red, or
`ci_watch.cancel_on_red: false` in the project config, keeps the old wait-until-done behaviour.

Memory kills (DL95): a failed step whose log tail has "exit code 137" or "Killed" is reported as
"killed for memory: the runner's cap is N", N read from the pool container on this machine with
`docker inspect` ("unknown" when it cannot be read). A job that failed in "Set up runner" / "Set up job"
after about 30 minutes is reported as a runner start-up failure pointing at the pool cap. Neither is a
lockfile problem, so neither report says so.

Python 3.11+, standard library only; `gh` is the one external tool.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script dir off sys.path
try:
    import runner_health  # noqa: E402
    import fallback_launch  # noqa: E402
except ModuleNotFoundError as _exc:
    _name = _exc.name or "a module"
    print("%s: %s.py is missing from %s. Run `delivery_ci_install.py update --track <track>` from the plugin, "
          "then commit scripts/delivery/." % (Path(__file__).name, _name.split(".")[0], Path(__file__).resolve().parent),
          file=sys.stderr)
    sys.exit(2)

OK_CONCLUSIONS = {"success", "skipped"}
LIST_FIELDS = "databaseId,workflowName,status,conclusion,event,headSha"
MAX_CONSECUTIVE_GH_ERRORS = 5
GIVE_UP_EXIT = 5  # DL247: gh failed too often in a row; the result is unknown
TRIM_IMAGES = ("postgres:16",)  # default for `ci.docker_trim_images`
TRIM_TIMEOUT_SECONDS = 600
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: a child process on Windows opens no console window
POST_RUN_TIMEOUT_SECONDS = 900
QUEUE_WARN_SECONDS = 600


class GhError(Exception):
    pass


class WorkflowNotFound(GhError):
    """`gh run list --workflow W` failed because workflow W does not exist."""


def is_missing_workflow(message: str) -> bool:
    low = message.lower()
    return "http 404" in low and "workflow" in low and "not found" in low


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


def gh_text(args: list[str]) -> str:
    """Run `gh` and return its text output ('' when it cannot be read)."""
    gh = shutil.which("gh") or "gh"
    try:
        proc = subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


KILLED = re.compile(r"exit code 137|\bKilled\b")
SETUP_STEPS = ("set up runner", "set up job")
SETUP_STALL_SECONDS = 25 * 60  # "about 30 minutes"


def pool_cap_text() -> str:
    """The live pool container's memory and CPU cap (`docker inspect`), or 'unknown'."""
    try:
        names = subprocess.run(["docker", "ps", "--filter", "label=dev.luismc.runner-pool", "--format", "{{.Names}}"],
                               capture_output=True, text=True, timeout=30)
        name = next((n for n in names.stdout.split() if n), "") if names.returncode == 0 else ""
        if not name:
            return "unknown"
        out = subprocess.run(["docker", "inspect", "--format", "{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}", name],
                             capture_output=True, text=True, timeout=30)
        mem, cpu = out.stdout.split()
        if out.returncode != 0 or not (mem.isdigit() and cpu.isdigit()):
            return "unknown"
    except (OSError, subprocess.SubprocessError, ValueError):
        return "unknown"
    mem_text = "no memory limit" if int(mem) == 0 else "%.1f GiB memory" % (int(mem) / 2 ** 30)
    return "%s, %.1f CPUs" % (mem_text, int(cpu) / 1e9)


def diagnose(job: dict, log_tail: str, cap: str | None = None) -> str | None:
    """DL95: a plain line for a job killed for memory or stalled at runner start-up, else None.
    `cap` is the pool cap text; it is read from docker only when a line is needed."""
    steps = job.get("steps", []) or []
    failed = [s for s in steps if s.get("conclusion") not in OK_CONCLUSIONS | {None, ""}]
    name = (failed[0].get("name") or "") if failed else ""
    if name.lower() in SETUP_STEPS:
        start, end = parse_time(job.get("startedAt")), parse_time(job.get("completedAt"))
        if start is not None and end is not None and end - start >= SETUP_STALL_SECONDS:
            return ("runner start-up failure: the job failed in \"%s\" after %s. Check the pool cap (%s) "
                    "and that the pool container is running; this is not a lockfile problem."
                    % (name, fmt_duration(end - start), cap if cap is not None else pool_cap_text()))
        return None
    if KILLED.search(log_tail or ""):
        return ("killed for memory: the runner's cap is %s. The step was stopped by the kernel, so the lockfile is not the "
                "cause. Raise the pool cap (run the setup again) or lower the shard's memory." % (cap if cap is not None else pool_cap_text()))
    return None


def repo_args(repo: str | None) -> list[str]:
    return ["--repo", repo] if repo else []


def list_runs(sha: str, workflow: str, repo: str | None) -> list[dict]:
    try:
        wf = ["--workflow", workflow] if workflow else []  # DL139: no name = every workflow
        data = gh_json(["run", "list", "--commit", sha, *wf,
                        "--limit", "100", "--json", LIST_FIELDS, *repo_args(repo)])
    except GhError as exc:
        if is_missing_workflow(str(exc)):
            raise WorkflowNotFound(str(exc)) from exc
        raise
    if not isinstance(data, list):
        raise GhError("gh run list did not return a list")
    # `--commit` already filters; this guards against a stale or wrong answer.
    return [r for r in data
            if isinstance(r, dict)
            and str(r.get("headSha", sha)).startswith(sha[:7])]


def add_other_workflows(runs: list[dict], sha: str, repo: str | None, warned: set | None = None) -> list[dict]:
    """DL139: the named workflow's runs plus every other workflow's run for the commit (one unfiltered
    `gh run list --commit`), so a required check in another workflow cannot fail unseen. Read once the named runs
    are complete. When the list cannot be read, a warning is printed once and the named runs decide."""
    try:
        extra = list_runs(sha, None, repo)
    except GhError as exc:
        if warned is not None and "other-runs" not in warned:
            warned.add("other-runs")
            print("ci_watch: warning: the other workflows' runs could not be read (%s)" % exc, file=sys.stderr)
        return runs
    seen = {r.get("databaseId") for r in runs if r.get("databaseId") is not None}
    out = list(runs)
    for r in extra:
        if r.get("databaseId") is None or r.get("databaseId") not in seen:
            out.append(r)
            seen.add(r.get("databaseId"))
    return out


def missing_workflow_message(workflow: str, repo: str | None, cause: str) -> str:
    """The exit-2 message: names the workflow and lists the repository's (best effort)."""
    head = f"ci_watch: workflow {workflow!r} does not exist in the repository ({cause})"
    try:
        data = gh_json(["workflow", "list", "--all", "--json", "name,path", *repo_args(repo)])
        rows = [w for w in data if isinstance(w, dict)] if isinstance(data, list) else []
        if not rows:
            return head + "\nci_watch: the repository lists no workflows; pass --workflow"
        lines = [f"  {w.get('path') or w.get('name')} ({w.get('name')})" for w in rows]
        return (head + "\nci_watch: workflows in the repository:\n" + "\n".join(lines)
                + "\nci_watch: pass one of them with --workflow")
    except GhError as exc:
        return head + f"\nci_watch: could not list the workflows ({exc}); pass the right --workflow"


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


def resolve_repo(repo: str | None) -> str | None:
    """DL247: OWNER/NAME for the whole watch: the --repo value, else `gh repo view`. None when unreadable."""
    if repo:
        return repo
    try:
        data = gh_json(["repo", "view", "--json", "nameWithOwner"])
    except GhError:
        return None
    name = data.get("nameWithOwner") if isinstance(data, dict) else None
    return name if isinstance(name, str) and re.fullmatch(r"[^/\s]+/[^/\s]+", name) else None


def resolve_sha(sha: str, repo: str | None) -> str | None:
    """The full 40-character sha for an abbreviated one: `gh run list --commit` matches
    full shas only, so a short one would wait for runs it can never see (DS94). Local git
    first, then the GitHub API; None when neither resolves it."""
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        return sha
    try:
        proc = subprocess.run(["git", "rev-parse", "--verify", "--quiet", sha + "^{commit}"],
                              capture_output=True, text=True, timeout=30)
        full = proc.stdout.strip().lower()
        if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", full):
            return full
    except (OSError, subprocess.SubprocessError):
        pass
    base = f"repos/{repo}" if repo else "repos/{owner}/{repo}"
    try:
        data = gh_json(["api", f"{base}/commits/{sha}"])
    except GhError:
        return None
    full = str(data.get("sha", "")).lower() if isinstance(data, dict) else ""
    return full if re.fullmatch(r"[0-9a-f]{40}", full) and full.startswith(sha) else None


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


def fallback_deps(repo: str | None, state: dict) -> "fallback_launch.Deps":
    """The real dependencies of the fallback hook; `state` keeps one launch per shard across polls."""
    return fallback_launch.Deps(str(config_root()), "origin", repo, gh_json=gh_json, state=state)


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
    # A job still queued or in progress is not failed (DL226).
    bad = [j for j in jobs if j.get("status", "completed") == "completed" and j.get("conclusion") not in OK_CONCLUSIONS]
    if not bad:
        print("    no failed job reported")
    for job in bad:
        print(f"    FAILED job: {job.get('name')} ({job.get('conclusion') or job.get('status')})")
        for step in job.get("steps", []) or []:
            if step.get("conclusion") not in OK_CONCLUSIONS | {None, ""}:
                print(f"      step: {step.get('name')} ({step.get('conclusion')})")
        try:
            tail = "\n".join(gh_text(["run", "view", str(rid), "--log-failed", *repo_args(repo)]).splitlines()[-60:])
            note = diagnose(job, tail)
        except Exception:  # noqa: BLE001 - a diagnosis must never break the failure report
            note = None
        if note:
            print(f"      {note}")


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


def ledger_root() -> Path:
    """DL132: the folder that holds .delivery/: the main checkout, found from git's common dir, so a run inside a
    git worktree writes the one ledger the merge hook reads. Falls back to the work tree's top folder."""
    import delivery_common as dc
    try:
        p = dc.run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], check=False)
        common = Path(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None
        if common is not None and common.name == ".git" and (common.parent / ".delivery").is_dir():
            return common.parent
    except Exception:  # noqa: BLE001
        pass
    return dc.repo_root()


def default_branch(repo: str | None = None) -> set[str]:
    """DL336: names of the default branch: `default_branch` in .delivery/config.json, else origin/HEAD, else main/master."""
    import delivery_common as dc
    names: set[str] = set()
    try:
        cfg = json.loads((ledger_root() / ".delivery" / "config.json").read_text(encoding="utf-8"))
        if isinstance(cfg.get("default_branch"), str) and cfg["default_branch"]:
            names.add(cfg["default_branch"])
    except Exception:  # noqa: BLE001
        pass
    if not names:
        try:
            out = dc.run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], check=False)
            if out.returncode == 0 and out.stdout.strip().startswith("refs/remotes/origin/"):
                names.add(out.stdout.strip()[len("refs/remotes/origin/"):])
        except Exception:  # noqa: BLE001
            pass
    return names or {"main", "master"}


def head_of(sha: str, repo: str | None) -> tuple[str | None, int | None]:
    """DL138: (branch, PR number) whose head is `sha`, from the local and remote branches at the commit (git only:
    no PR lookup, so the PR number stays None and the ledger matches the train by branch or by its recorded head).
    DL336: full ref names, so origin/HEAD is dropped; the default branch is dropped too.
    (None, None) when no branch is found; never raises."""
    try:
        import delivery_common as dc
        skip = default_branch(repo) | {"HEAD"}
        out = dc.run_git(["for-each-ref", "--points-at", sha, "--format=%(refname)", "refs/heads", "refs/remotes"],
                         check=False)
        for ref in out.stdout.split():
            if ref.startswith("refs/heads/"):
                name = ref[len("refs/heads/"):]
            elif ref.startswith("refs/remotes/"):
                parts = ref[len("refs/remotes/"):].split("/", 1)
                if len(parts) < 2:
                    continue
                name = parts[1]
            else:
                continue
            if name.rsplit("/", 1)[-1] == "HEAD" or name in skip:
                continue
            return name, None
    except Exception:  # noqa: BLE001
        pass
    return None, None


def ledger_links(root: Path, sha: str) -> bool:
    """DL265: True when a ledger train records `sha` as its CI head. A missing or unreadable ledger counts as linked."""
    try:
        led = json.loads((Path(root) / ".delivery" / "ledger.json").read_text(encoding="utf-8"))
        return any((t.get("ci") or {}).get("head_sha") == sha for t in led.get("trains", []))
    except Exception:  # noqa: BLE001
        return True


def ledger_ci(sha: str, state: str, repo: str | None = None) -> None:
    """Best effort: record the decision in the delivery ledger (no-op without the plugin). DL132 the main
    checkout's ledger; DL138 the train is matched by branch or PR head and made when none exists."""
    try:
        import delivery_common as dc
        root = ledger_root()
        branch, pr = head_of(sha, repo)
        kw = {"branch": branch, "pr": pr, "create": bool(branch)}
        if not dc.ledger_record(root, "ci", sha=sha, state=state, by="ci_watch.py", **kw):
            return
        if not ledger_links(root, sha):
            print("ci_watch: no train in the ledger links %s; the result was not recorded; link it with "
                  "delivery_ledger.py link --pr N --sha %s --branch <branch>, then run ci_watch again" % (sha, sha),
                  file=sys.stderr)
    except Exception:  # noqa: BLE001
        return


def config_root() -> Path:
    """The folder hooks run from: the repository root, else the current folder."""
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                              text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def load_post_run(config: str | None, root: Path) -> tuple[list[str], float]:
    """The `ci_watch.post_run` commands and their timeout from the project config.

    A missing file or key means no hooks; a malformed one is logged and means no hooks."""
    path = Path(config) if config else root / ".delivery" / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], POST_RUN_TIMEOUT_SECONDS
    except (OSError, ValueError) as exc:
        print(f"ci_watch: post_run hooks not read: {path} is unreadable ({exc})", file=sys.stderr)
        return [], POST_RUN_TIMEOUT_SECONDS
    section = data.get("ci_watch") if isinstance(data, dict) else None
    if not isinstance(section, dict) or "post_run" not in section:
        return [], POST_RUN_TIMEOUT_SECONDS
    hooks = section["post_run"]
    if not isinstance(hooks, list) or not all(isinstance(h, str) and h.strip() for h in hooks):
        print("ci_watch: post_run hooks not run: ci_watch.post_run must be a list of non-empty "
              "strings", file=sys.stderr)
        return [], POST_RUN_TIMEOUT_SECONDS
    timeout = section.get("post_run_timeout_seconds", POST_RUN_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        timeout = POST_RUN_TIMEOUT_SECONDS
    return list(hooks), float(timeout)


def hook_argv(template: str, values: dict[str, str]) -> list[str]:
    """Split the command first, then fill the placeholders word by word (no shell, no injection)."""
    argv = shlex.split(template)
    if not argv:
        raise ValueError("empty command")
    out = []
    for word in argv:
        for name, value in values.items():
            word = word.replace("{" + name + "}", value)
        out.append(word)
    if out[0] in ("python", "python3") and shutil.which(out[0]) is None:
        out[0] = sys.executable
    return out


def run_post_run_hooks(hooks: list[str], runs: list[dict], sha: str, root: Path,
                       timeout: float = POST_RUN_TIMEOUT_SECONDS, run=subprocess.run) -> int:
    """Run every hook for every run, in order; returns how many failed. Never raises."""
    failed = 0
    for item in runs:
        values = {"run_id": str(item.get("databaseId", "")), "head": sha,
                  "conclusion": str(item.get("conclusion") or ""),
                  "workflow": str(item.get("workflowName") or "")}
        for template in hooks:
            try:
                argv = hook_argv(template, values)
                proc = run(argv, cwd=str(root), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
                if proc.stdout:
                    print(proc.stdout.rstrip("\n"), flush=True)
                if proc.stderr:
                    print(proc.stderr.rstrip("\n"), file=sys.stderr, flush=True)
                if proc.returncode != 0:
                    failed += 1
                    print(f"ci_watch: post_run hook failed (exit {proc.returncode}): {template} "
                          f"[run {values['run_id']}]", file=sys.stderr, flush=True)
            except Exception as exc:  # noqa: BLE001 - a hook must never change the verdict
                failed += 1
                print(f"ci_watch: post_run hook failed ({type(exc).__name__}: {exc}): {template} "
                      f"[run {values['run_id']}]", file=sys.stderr, flush=True)
    return failed


def trim_command(image: str) -> list[str]:
    """fstrim of every mounted filesystem of the Docker VM, from a privileged container in its
    namespaces (no Docker restart needed)."""
    return ["docker", "run", "--rm", "--pull=never", "--privileged", "--pid=host", image,
            "nsenter", "-t", "1", "-m", "--", "fstrim", "-av"]


def trimmed_gib(output: str) -> float:
    """Sum of the sizes fstrim reports ("/mnt/x: 990 GiB (1063 bytes) trimmed on ...")."""
    units = {"B": 1 / 2**30, "KiB": 1 / 2**20, "MiB": 1 / 2**10, "GiB": 1.0, "TiB": 1024.0}
    total = 0.0
    for m in re.finditer(r":\s*([\d.]+)\s*(B|KiB|MiB|GiB|TiB)\b[^\n]*trimmed", output):
        total += float(m.group(1)) * units[m.group(2)]
    return total


def load_docker_trim(config: str | None, root: Path) -> tuple[bool, tuple[str, ...]]:
    """`ci.docker_trim` (default false) and `ci.docker_trim_images` from the project config.

    A missing or unreadable file means off."""
    path = Path(config) if config else root / ".delivery" / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, TRIM_IMAGES
    ci = data.get("ci") if isinstance(data, dict) else None
    if not isinstance(ci, dict) or ci.get("docker_trim") is not True:
        return False, TRIM_IMAGES
    images = ci.get("docker_trim_images")
    if not isinstance(images, list) or not images or not all(isinstance(i, str) and i for i in images):
        images = list(TRIM_IMAGES)
    return True, tuple(images)


def trim_docker_disk(is_windows: bool | None = None, run=subprocess.run, which=shutil.which,
                     images: tuple[str, ...] = TRIM_IMAGES) -> str:
    """Trim Docker Desktop's data disk once; returns the logged line, or "" when skipped. Never raises."""
    try:
        windows = os.name == "nt" if is_windows is None else is_windows
        if not windows:
            return ""
        if which("docker") is None:
            return ""
        flags = {"creationflags": NO_WINDOW}
        image = None
        for candidate in images:
            probe = run(["docker", "image", "inspect", candidate], capture_output=True, text=True,
                        timeout=60, **flags)
            if probe.returncode == 0:
                image = candidate
                break
        if image is None:
            return "ci_watch: docker disk not trimmed: no image present (" + ", ".join(images) + ")"
        proc = run(trim_command(image), capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=TRIM_TIMEOUT_SECONDS, **flags)
        if proc.returncode != 0:
            return f"ci_watch: docker disk not trimmed: fstrim failed ({proc.returncode})"
        return f"ci_watch: docker disk trimmed: {trimmed_gib(proc.stdout or ''):.0f} GiB"
    except Exception as exc:  # noqa: BLE001 - the trim must never break the watch
        return f"ci_watch: docker disk not trimmed: {type(exc).__name__}"


def finish(code: int, runs: list[dict], sha: str, args: argparse.Namespace) -> int:
    """The exit path once the runs are complete: trim Docker's disk (only when `ci.docker_trim` is true),
    run the post-run hooks, keep the exit code."""
    if not getattr(args, "no_trim", False):
        try:
            enabled, images = load_docker_trim(getattr(args, "config", None), config_root())
            line = trim_docker_disk(images=images) if enabled else ""
            if line:
                print(line, flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"ci_watch: docker trim skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    if not args.no_post_run:
        try:
            root = config_root()
            hooks, timeout = load_post_run(args.config, root)
            if hooks:
                run_post_run_hooks(hooks, runs, sha, root, timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"ci_watch: post_run hooks skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return code


def list_statuses(sha: str, repo: str | None) -> dict:
    """{context: state} of the newest commit status of each context (CI option c)."""
    data = gh_json(["api", "repos/%s/commits/%s/status" % (repo or "{owner}/{repo}", sha)])
    if not isinstance(data, dict) or not isinstance(data.get("statuses"), list):
        raise GhError("gh api commit status did not return a status list")
    return {st["context"]: st.get("state") for st in data["statuses"]
            if isinstance(st, dict) and isinstance(st.get("context"), str)}


HELD_CONTEXT = "rerun-first/held"  # DL183: same name as STATUS_CONTEXT in ci_rerun_first.py


def rerun_first_on() -> bool:
    """True only when the project's scripts/delivery/ci-areas.json has "rerun_first": true. Anything else
    (no file, bad JSON, key off) is False, so a project that did not opt in costs no extra gh call."""
    try:
        with open(config_root() / "scripts" / "delivery" / "ci-areas.json", encoding="utf-8") as fh:
            return json.load(fh).get("rerun_first") is True
    except (OSError, ValueError, AttributeError):
        return False


def waiting_for_held_jobs(sha: str, runs: list[dict], repo: str | None) -> bool:
    """DL183: true while the head's `rerun-first/held` status is pending and the dispatched run (event
    workflow_dispatch) has not completed. Without the status (no rerun_first) this is false and nothing
    changes. A status that cannot be read counts as not waiting."""
    if not rerun_first_on():
        return False
    try:
        if list_statuses(sha, repo).get(HELD_CONTEXT) != "pending":
            return False
    except GhError:
        return False
    return not any(r.get("event") == "workflow_dispatch" and r.get("status") == "completed" for r in runs)


def watch_statuses(sha: str, args: argparse.Namespace) -> int:
    """Wait for the commit statuses of the cloud shards (option c). Reads results the way the watcher does."""
    deadline = time.monotonic() + args.timeout
    errors = 0
    last_state = ""
    while True:
        state = ""
        try:
            got = list_statuses(sha, args.repo)
            errors = 0
        except GhError as exc:
            errors += 1
            state = f"gh error ({errors}): {exc}"
            if errors >= MAX_CONSECUTIVE_GH_ERRORS:
                print(f"ci_watch: giving up, gh failed {errors} times in a row: {exc}", file=sys.stderr)
                return GIVE_UP_EXIT
            got = None
        if got is not None:
            bad = [c for c in args.context if got.get(c) in ("failure", "error")]
            waiting = [c for c in args.context if got.get(c) not in ("success", "failure", "error")]
            if bad:
                print(f"ci_watch: {len(bad)} of {len(args.context)} status(es) for {sha[:10]} did not "
                      f"succeed: {', '.join(bad)}")
                ledger_ci(sha, "failure", args.repo)
                return 1
            if not waiting:
                print(f"ci_watch: {len(args.context)} status(es) for {sha[:10]} succeeded")
                ledger_ci(sha, "success", args.repo)
                return 0
            state = f"{len(waiting)} of {len(args.context)} status(es) not posted yet: {', '.join(waiting)}"
        if state != last_state:
            print(f"ci_watch: waiting, {state}", flush=True)
            last_state = state
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"ci_watch: timed out after {args.timeout:g}s, {state}", file=sys.stderr)
            return 4
        time.sleep(min(args.interval, remaining))


MIN_INTERVAL = 30.0          # DL235: seconds; the default is 60
DEFAULT_INTERVAL = 60.0
DEFAULT_MAX_INTERVAL = 120.0
DEFAULT_MIN_REMAINING = 200  # below this many REST calls left, wait for the reset instead of polling


def effective_interval(value: float) -> float:
    """DL235: a value under 1 s is for tests (no floor, no quota read); anything else is at least MIN_INTERVAL."""
    return value if value < 1 else max(value, MIN_INTERVAL)


def next_delay(base: float, current: float, queued_only: bool, cap: float) -> float:
    """DL235: back off (x1.5, up to cap) while every watched run is still queued; else the base interval."""
    if not queued_only or base == 0:
        return base
    return min(max(cap, base), current * 1.5)


def read_rate_limit(repo: str | None = None) -> tuple[int, float] | None:
    """(core.remaining, core.reset epoch) from `gh api rate_limit` (free), None when unreadable."""
    try:
        data = gh_json(["api", "rate_limit"])
        core = data["resources"]["core"]
        return int(core["remaining"]), float(core["reset"])
    except (GhError, KeyError, TypeError, ValueError):
        return None


def quota_guard(repo: str | None, min_remaining: int, sleep=None, now=None, read=None) -> float:
    """DL235: before a poll cycle, sleep until the quota resets when it is low.
    Returns the seconds slept (the caller adds them to the deadline). Never fails."""
    sleep = sleep or time.sleep
    now = now or time.time
    got = (read or read_rate_limit)(repo)
    if got is None or got[0] >= min_remaining:
        return 0.0
    wait = max(0.0, got[1] - now()) + 1.0
    clock = time.strftime("%H:%M:%S", time.localtime(got[1]))
    print(f"ci_watch: GitHub quota low ({got[0]} calls left); waiting until it resets at {clock}", flush=True)
    sleep(wait)
    return wait


def run_commit(run_id: str, repo: str | None) -> str | None:
    """DL235: the head commit of a workflow run (one call), None when it cannot be read."""
    try:
        data = gh_json(["run", "view", run_id, "--json", "headSha", *repo_args(repo)])
    except GhError:
        return None
    sha = data.get("headSha") if isinstance(data, dict) else None
    return sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else None


RED_CONCLUSIONS = {"failure", "timed_out", "cancelled"}
TRAIN_BRANCH_RE = r"^release/"


def load_cancel_config(config: str | None, root: Path) -> tuple[bool, str]:
    """DL306: (`ci_watch.cancel_on_red` default True, top-level `train_branch_re` default ^release/)."""
    path = Path(config) if config else root / ".delivery" / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, TRAIN_BRANCH_RE
    if not isinstance(data, dict):
        return True, TRAIN_BRANCH_RE
    section = data.get("ci_watch")
    flag = section.get("cancel_on_red", True) if isinstance(section, dict) else True
    pattern = data.get("train_branch_re")
    return flag is not False, pattern if isinstance(pattern, str) and pattern else TRAIN_BRANCH_RE


def is_train_head(run_id: object, pattern: str, repo: str | None) -> bool:
    """True when the run's head branch matches the train pattern. Unreadable means no."""
    try:
        data = gh_json(["run", "view", str(run_id), "--json", "headBranch", *repo_args(repo)])
        branch = data.get("headBranch") if isinstance(data, dict) else None
        return isinstance(branch, str) and re.search(pattern, branch) is not None
    except (GhError, re.error):
        return False


def red_jobs(run: dict, repo: str | None) -> list[dict]:
    """Jobs of a run that have already ended red (completed with failure, timed_out or cancelled)."""
    if run.get("status") == "completed":
        return [{"name": "(whole run)", "conclusion": run.get("conclusion")}] \
            if run.get("conclusion") in RED_CONCLUSIONS else []
    data = gh_json(["run", "view", str(run.get("databaseId")), "--json", "jobs", *repo_args(repo)])
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    return [j for j in jobs if isinstance(j, dict) and j.get("status", "completed") == "completed"
            and j.get("conclusion") in RED_CONCLUSIONS]


def cancel_on_red(sha: str, runs: list[dict], args: argparse.Namespace, st: dict) -> bool:
    """DL306: when a train head has a red job, cancel its other runs. True when the watch must end red."""
    if args.no_cancel_on_red:
        return False
    if "cancel_cfg" not in st:
        st["cancel_cfg"] = load_cancel_config(args.config, config_root())
    enabled, pattern = st["cancel_cfg"]
    if not enabled or st.get("train") is False:
        return False
    ours = st.setdefault("cancelled", set())
    red: list[tuple[dict, list[dict]]] = []
    for run in runs:
        if run.get("databaseId") in ours:
            continue
        try:
            jobs = red_jobs(run, args.repo)
        except GhError:
            continue
        if jobs:
            red.append((run, jobs))
    if not red:
        return False
    if "train" not in st:
        st["train"] = is_train_head(runs[0].get("databaseId"), pattern, args.repo)
    if not st["train"]:
        return False
    print(f"ci_watch: red on train head {sha[:10]}:")
    for run, jobs in red:
        for job in jobs:
            print(f"  FAILED job: {job.get('name')} ({job.get('conclusion')}) in run "
                  f"{run.get('databaseId')} ({run.get('workflowName')})")
    for run in runs:
        rid = run.get("databaseId")
        if run.get("status") == "completed" or rid is None:
            continue
        try:
            gh_json(["run", "cancel", str(rid), *repo_args(args.repo)])
        except GhError as exc:
            # gh prints no JSON for cancel; only a real error is logged.
            if "invalid JSON" not in str(exc):
                print(f"ci_watch: could not cancel run {rid}: {exc}", file=sys.stderr)
                continue
        ours.add(rid)
        print(f"ci_watch: cancelled run {rid} ({run.get('workflowName')}), red run on this head")
    print(f"ci_watch: push freeze lifted for {sha[:10]}: the cancelled runs end, a fix push is allowed")
    st["red_runs"] = [r for r, _ in red]
    return True


def poll_commit(sha: str, args: argparse.Namespace, st: dict) -> int | None:
    """DL235: one poll of one commit. Returns the exit code once decided, None while it waits.
    `st` carries errors, warned, fallback_state, state and queued_only between polls."""
    errors = st["errors"]
    warned = st["warned"]
    fallback_state = st["fallback_state"]
    state = ""
    st["queued_only"] = False
    try:
        state = ""
        decided = False
        try:
            runs = list_runs(sha, args.workflow, args.repo)
            errors = 0
        except WorkflowNotFound as exc:
            print(missing_workflow_message(args.workflow, args.repo, str(exc)), file=sys.stderr)
            return 2
        except GhError as exc:
            errors += 1
            state = f"gh error ({errors}): {exc}"
            if errors >= MAX_CONSECUTIVE_GH_ERRORS:
                print(f"ci_watch: giving up, gh failed {errors} times in a row: {exc}",
                      file=sys.stderr)
                return GIVE_UP_EXIT
            runs = None
        if runs is not None:
            pending = [r for r in runs if r.get("status") != "completed"]
            st["queued_only"] = not runs or all(r.get("status") == "queued" for r in pending) and bool(pending)
            if not runs:
                state = f"no {args.workflow} run for {sha[:10]} yet"
            elif pending:
                state = f"{len(pending)} of {len(runs)} run(s) not completed"
                warn_queued_jobs(pending, args.repo, warned, args.queue_warn_seconds)
                if cancel_on_red(sha, runs if args.only_workflow else add_other_workflows(runs, sha, args.repo, warned),
                                 args, st):
                    for run in st["red_runs"]:
                        print_failed_jobs(run, args.repo)
                    ledger_ci(sha, "failure", args.repo)
                    return finish(1, runs, sha, args)
                if not args.no_fallback:
                    fallback_launch.check_and_launch(
                        sha, pending, fallback_deps(args.repo, fallback_state))
            else:
                if not args.only_workflow:
                    runs = add_other_workflows(runs, sha, args.repo, warned)
                pending = [r for r in runs if r.get("status") != "completed"]
                # A run still queued or in progress has no conclusion yet: it is never a failure (DL226).
                bad = [r for r in runs if r.get("status") == "completed" and r.get("conclusion") not in OK_CONCLUSIONS]
                decided = not pending
                if pending:
                    state = f"{len(pending)} of {len(runs)} run(s) not completed (other workflows)"
                elif not bad and waiting_for_held_jobs(sha, runs, args.repo):
                    state = "waiting for held jobs (run 2)"
                    decided = False
            if decided and not pending:
                try:
                    idle = [r for r in runs if r not in bad and not executed_jobs(r, args.repo)]
                    # Skipped runs only matter when the head belongs to an open PR.
                    if idle and not bad and len(idle) == len(runs) and has_open_pr(sha, args.repo):
                        state = (f"no real run yet for {sha[:10]}: only skipped {args.workflow} "
                                 f"run(s) so far, waiting for the pull_request run")
                        decided = False
                    st["late_errors"] = 0
                except GhError as exc:
                    # The run list above succeeded and reset `errors`, so this step counts its own failures.
                    st["late_errors"] = late = st.get("late_errors", 0) + 1
                    state = f"gh error ({late}): {exc}"
                    if late >= MAX_CONSECUTIVE_GH_ERRORS:
                        print(f"ci_watch: giving up, gh failed {late} times in a row: {exc}",
                              file=sys.stderr)
                        return GIVE_UP_EXIT
                    decided = False
            if decided:
                if not bad:
                    print(f"ci_watch: {len(runs)} {args.workflow} run(s) for {sha[:10]} "
                          "succeeded")
                    print_slowest_job_summary(runs, args.repo)
                    ledger_ci(sha, "success", args.repo)
                    return finish(0, runs, sha, args)
                print(f"ci_watch: {len(bad)} of {len(runs)} {args.workflow} run(s) for "
                      f"{sha[:10]} did not succeed")
                for run in bad:
                    print_failed_jobs(run, args.repo)
                print_slowest_job_summary(runs, args.repo)
                ledger_ci(sha, "failure", args.repo)
                return finish(1, runs, sha, args)
        return None
    finally:
        st["errors"] = errors
        st["state"] = state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Wait for the CI workflow runs of a commit (never reads PR checks).")
    ap.add_argument("sha", nargs="*", help="commit sha(s) whose runs to watch; one process watches them all")
    ap.add_argument("--run", action="append", default=[], metavar="RUN_ID",
                    help="workflow run id to watch (its commit is watched); repeat it for several")
    ap.add_argument("--workflow", default="ci.yml",
                    help="workflow file name or name (default ci.yml); a workflow that "
                         "does not exist exits 2 at once and lists the repository's workflows")
    ap.add_argument("--only-workflow", action="store_true",
                    help="watch only the --workflow runs; by default every workflow run for the commit is "
                         "watched and any failure fails the watch")
    ap.add_argument("--timeout", type=float, default=3600,
                    help="seconds to wait before giving up with exit 4 (default 3600)")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                    help="seconds between polls (default 60, minimum 30; under 1 polls at once, for tests)")
    ap.add_argument("--max-interval", type=float, default=DEFAULT_MAX_INTERVAL,
                    help="the poll interval grows up to this while every run is still queued (default 120)")
    ap.add_argument("--min-remaining", type=int, default=DEFAULT_MIN_REMAINING,
                    help="below this many GitHub REST calls left, wait for the quota reset (default 200)")
    ap.add_argument("--queue-warn-seconds", type=float, default=QUEUE_WARN_SECONDS,
                    help="warn about a job queued this long with no runner for its labels "
                         "(default 600)")
    ap.add_argument("--context", action="append", default=[],
                    help="CI option c (cloud sessions): watch this commit status context instead of a "
                         "workflow; repeat it for several. Same exit codes: 0 all success, 1 one failed, "
                         "4 timed out")
    ap.add_argument("--repo", help="OWNER/NAME (default: the current repository)")
    ap.add_argument("--config", help="project config with ci_watch.post_run "
                                     "(default: .delivery/config.json in the repository root)")
    ap.add_argument("--no-fallback", action="store_true",
                    help="do not start the Option 4 fallback for shards that wait too long (ci.fallback)")
    ap.add_argument("--no-trim", action="store_true",
                    help="do not trim Docker Desktop's data disk after the runs complete "
                         "(runs only on Windows, and only when .delivery/config.json has ci.docker_trim: true)")
    ap.add_argument("--no-cancel-on-red", action="store_true",
                    help="on a train head, do not cancel the other runs when one job fails "
                         "(config ci_watch.cancel_on_red: false does the same)")
    ap.add_argument("--no-post-run", action="store_true",
                    help="do not run the ci_watch.post_run hooks of the project config")
    args = ap.parse_args(argv)

    if not args.sha and not args.run:
        print("ci_watch: give a commit sha or --run RUN_ID", file=sys.stderr)
        return 2
    for item in args.sha:
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", item):
            print(f"ci_watch: {item!r} is not a commit sha", file=sys.stderr)
            return 2
    for item in args.run:
        if not item.isdigit():
            print(f"ci_watch: {item!r} is not a run id", file=sys.stderr)
            return 2
    if args.timeout <= 0 or args.interval < 0:
        print("ci_watch: --timeout must be positive and --interval not negative",
              file=sys.stderr)
        return 2
    if shutil.which("gh") is None:
        print("ci_watch: the GitHub CLI (gh) is not installed or not on PATH",
              file=sys.stderr)
        return 2

    args.repo = resolve_repo(args.repo)
    if not args.repo:
        print("ci_watch: could not resolve the repository (gh repo view failed); pass --repo OWNER/NAME",
              file=sys.stderr)
        return 2
    shas: list[str] = []
    for item in args.sha:
        full = resolve_sha(item.lower(), args.repo)
        if full is None:
            print(f"ci_watch: could not resolve {item} to a full commit sha "
                  "(`gh run list --commit` matches full shas only); pass all 40 characters",
                  file=sys.stderr)
            return 2
        shas.append(full)
    for item in args.run:
        full = run_commit(item, args.repo)
        if full is None:
            print(f"ci_watch: could not read the commit of run {item}", file=sys.stderr)
            return 2
        shas.append(full)
    shas = list(dict.fromkeys(shas))
    sha = shas[0]
    if args.context:
        codes = [watch_statuses(item, args) for item in shas]
        return max(codes)
    watches = []
    for sha in shas:
        watches.append((sha, {"errors": 0, "warned": set(), "fallback_state": {}, "state": "",
                              "queued_only": False, "last_state": ""}))
    deadline = time.monotonic() + args.timeout
    base = effective_interval(args.interval)
    delay = base
    codes = []
    while True:
        if base >= 1:
            deadline += quota_guard(args.repo, args.min_remaining)
        for sha, st in list(watches):
            code = poll_commit(sha, args, st)
            if code is not None:
                watches.remove((sha, st))
                codes.append(code)
                continue
            if st["state"] != st["last_state"]:
                prefix = f"{sha[:10]}: " if len(shas) > 1 else ""
                print(f"ci_watch: waiting, {prefix}{st['state']}", flush=True)
                st["last_state"] = st["state"]
        if not watches:
            return max(codes)
        delay = next_delay(base, delay, all(st["queued_only"] for _, st in watches), args.max_interval)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            for sha, st in watches:
                print(f"ci_watch: timed out after {args.timeout:g}s, {sha[:10]}: {st['state']}", file=sys.stderr)
            return 4
        time.sleep(min(delay, remaining))


if __name__ == "__main__":
    sys.exit(main())
