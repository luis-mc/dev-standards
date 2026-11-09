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

Exit codes (shared by the delivery scripts): 0 every run succeeded or was
skipped (see above), 1 any other conclusion (the failed jobs are printed), 2 usage
error or `gh` missing or unusable, 4 timed out ("no real run yet" when only skipped
runs exist for a pull request head). It never exits 0 when it could not decide.
A workflow that does not exist in the repository (HTTP 404, "workflow ... not found") is a
usage error, not a transient one: it exits 2 at once, without retrying, and lists the
repository's workflows so the caller can pass the right --workflow. Any other gh error is
retried and gives up with exit 2 after five in a row.

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
        data = gh_json(["run", "list", "--commit", sha, "--workflow", workflow,
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
    bad = [j for j in jobs if j.get("conclusion") not in OK_CONCLUSIONS]
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


def ledger_ci(sha: str, state: str) -> None:
    """Best effort: record the decision in the delivery ledger (no-op without the plugin)."""
    try:
        import delivery_common as dc
        dc.ledger_record(dc.repo_root(), "ci", sha=sha, state=state, by="ci_watch.py")
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
                return 2
            got = None
        if got is not None:
            bad = [c for c in args.context if got.get(c) in ("failure", "error")]
            waiting = [c for c in args.context if got.get(c) not in ("success", "failure", "error")]
            if bad:
                print(f"ci_watch: {len(bad)} of {len(args.context)} status(es) for {sha[:10]} did not "
                      f"succeed: {', '.join(bad)}")
                ledger_ci(sha, "failure")
                return 1
            if not waiting:
                print(f"ci_watch: {len(args.context)} status(es) for {sha[:10]} succeeded")
                ledger_ci(sha, "success")
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Wait for the CI workflow runs of a commit (never reads PR checks).")
    ap.add_argument("sha", help="commit sha whose runs to watch")
    ap.add_argument("--workflow", default="ci.yml",
                    help="workflow file name or name (default ci.yml); a workflow that "
                         "does not exist exits 2 at once and lists the repository's workflows")
    ap.add_argument("--timeout", type=float, default=3600,
                    help="seconds to wait before giving up with exit 4 (default 3600)")
    ap.add_argument("--interval", type=float, default=30,
                    help="seconds between polls (default 30)")
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
    ap.add_argument("--no-post-run", action="store_true",
                    help="do not run the ci_watch.post_run hooks of the project config")
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

    sha = resolve_sha(args.sha.lower(), args.repo)
    if sha is None:
        print(f"ci_watch: could not resolve {args.sha} to a full commit sha "
              "(`gh run list --commit` matches full shas only); pass all 40 characters",
              file=sys.stderr)
        return 2
    if args.context:
        return watch_statuses(sha, args)
    deadline = time.monotonic() + args.timeout
    errors = 0
    last_state = ""
    warned: set = set()
    fallback_state: dict = {}
    while True:
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
                return 2
            runs = None
        if runs is not None:
            pending = [r for r in runs if r.get("status") != "completed"]
            if not runs:
                state = f"no {args.workflow} run for {sha[:10]} yet"
            elif pending:
                state = f"{len(pending)} of {len(runs)} run(s) not completed"
                warn_queued_jobs(pending, args.repo, warned, args.queue_warn_seconds)
                if not args.no_fallback:
                    fallback_launch.check_and_launch(
                        sha, pending, fallback_deps(args.repo, fallback_state))
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
                    return finish(0, runs, sha, args)
                print(f"ci_watch: {len(bad)} of {len(runs)} {args.workflow} run(s) for "
                      f"{sha[:10]} did not succeed")
                for run in bad:
                    print_failed_jobs(run, args.repo)
                print_slowest_job_summary(runs, args.repo)
                ledger_ci(sha, "failure")
                return finish(1, runs, sha, args)
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
