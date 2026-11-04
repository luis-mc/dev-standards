#!/usr/bin/env python3
"""Start the fallback for shards that waited too long for their own runner (Option 4, CIR10 S8).

    fallback_launch.py sweep  [--root DIR] [--repo OWNER/NAME] [--dry-run]
    fallback_launch.py launch --sha SHA --shard ID [--kind cloud|github-hosted] [--root DIR] [--repo OWNER/NAME]

Who calls it:
  * `ci_watch.py` calls `check_and_launch` on every poll while runs are pending. That is the watcher of the
    session that opened the run.
  * `sweep` is what the hourly safety-net routine runs (templates/shared/routines/ci-fallback-watch.json).
    An unattended fallback can therefore start up to an hour late. There is no watchdog job in the workflow.
  * `launch` starts one shard by hand (the test-repository recipe uses it).

Config, `.delivery/config.json` -> `ci.fallback`. The core's keys are in ci_fallback.py (`options` per OS:
`cloud` or `github-hosted`; `after_min` = X with no default; optional caps). This file adds the launchers' keys:
  "cloud":  {"fire_url": "https://...", "token_env": "NAME"},        # the routine's API trigger
  "hosted": {"workflow": "ci-fallback.yml", "ref": "main"}

Rules:
  * Only runner waits count: a job is waiting while GitHub reports it `queued`. A run held back by the
    one-at-a-time setting has no job yet, so it never counts. GitHub-hosted labels never count.
  * Wait under X: nothing. Over X: one launch per waiting shard, once. The launch is reserved first by creating
    the branch `ci-fallback/<sha>/<shard>`; a second create is refused by git, so the session watcher and the
    hourly routine never launch the same shard twice.
  * A shard that already has a claim (`ci-claim/<sha>/<shard>/*`) or a result branch is never launched.
  * Windows shards use hosted Windows only (cloud sessions are Linux) and only for a ready pull request.
  * Caps are optional and counted by the core (`ci_fallback.fallback_gate`) before the launch. When a cap is hit
    nothing is launched and one warning is printed per commit and kind.
  * The launched job takes the claim last, just before its tests (`fallback_run.py`). First claim wins.

Python 3.11+, standard library only; `git` is needed, `gh` for the hosted launch and the sweep.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script dir off sys.path

import ci_fallback  # noqa: E402  (the Option 4 core: settings, decision, caps, claim; DL23)

LAUNCH_PREFIX = "ci-fallback"
CLAIM_PREFIX = "ci-claim"
MAX_LAUNCH_FAILURES = 3
KINDS = ("cloud", "github-hosted")
FULL_SHA = re.compile(r"[0-9a-f]{40}")


# ---------------------------------------------------------------- config

def read_config(root: str) -> dict:
    try:
        with open(os.path.join(root, ".delivery", "config.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def settings_from(cfg: dict) -> dict | None:
    """The fallback settings, or None when the fallback is off (then nothing ever launches).

    The core's keys (`options` per OS, `after_min`, caps) are read by `ci_fallback.fallback_settings`; this
    adds the launchers' own keys: `ci.fallback.cloud` (fire_url, token_env) and `ci.fallback.hosted`
    (workflow, ref). Kind names are the core's: `cloud` and `github-hosted`."""
    fb_all = ci_fallback.fallback_settings(cfg)
    if not fb_all["enabled"]:
        return None
    ci = _dict(cfg.get("ci"))
    fb = _dict(ci.get("fallback"))
    cloud = _dict(ci.get("cloud"))
    timeout = cloud.get("shard_timeout_min")
    return {
        "core": fb_all, "cfg": cfg,
        "cloud": _dict(fb.get("cloud")),
        "hosted": _dict(fb.get("hosted")),
        "table": ci.get("shard_table") if isinstance(ci.get("shard_table"), str) else "scripts/delivery/ci-shards.json",
        "prefix": cloud.get("results_prefix") if isinstance(cloud.get("results_prefix"), str) and cloud.get("results_prefix") else "ci-result",
        "timeout_min": timeout if isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout >= 1 else 60,
    }


def load_shards(root: str, st: dict) -> list[dict]:
    with open(os.path.join(root, *st["table"].split("/")), encoding="utf-8") as f:
        table = json.load(f)
    return [s for s in table.get("shards", []) if isinstance(s, dict) and isinstance(s.get("id"), str)]


# ---------------------------------------------------------------- git helpers

def git(root: str, *args, input_=None):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, input=input_, check=False)


def remote_has(root: str, remote: str, pattern: str) -> bool:
    r = git(root, "ls-remote", "--heads", remote, "refs/heads/" + pattern)
    return r.returncode == 0 and bool(r.stdout.strip())


def reserve_launch(root: str, remote: str, sha: str, shard: str) -> bool:
    """Create the branch ci-fallback/<sha>/<shard>. True only for the caller whose create won.

    Every call makes a different commit (the time is in the message), so a second push to the same
    name is not a fast-forward and git refuses it. Any failure counts as not reserved."""
    tree = git(root, "mktree", input_="")
    if tree.returncode:
        return False
    env_msg = "fallback launch %s %s %s %d" % (shard, sha[:10], os.getpid(), time.time_ns())
    env = dict(os.environ, GIT_AUTHOR_NAME="ci-fallback", GIT_AUTHOR_EMAIL="ci-fallback@localhost",
               GIT_COMMITTER_NAME="ci-fallback", GIT_COMMITTER_EMAIL="ci-fallback@localhost")
    c = subprocess.run(["git", "commit-tree", tree.stdout.strip(), "-m", env_msg], cwd=root, env=env,
                       capture_output=True, text=True, check=False)
    if c.returncode:
        return False
    p = git(root, "push", "-q", remote, "%s:refs/heads/%s/%s/%s" % (c.stdout.strip(), LAUNCH_PREFIX, sha, shard))
    return p.returncode == 0


def release_launch(root: str, remote: str, sha: str, shard: str) -> None:
    """Delete the reservation again (a cap paused the launch, or the launch call failed). Best effort."""
    git(root, "push", "-q", remote, "--delete", "refs/heads/%s/%s/%s" % (LAUNCH_PREFIX, sha, shard))


# ---------------------------------------------------------------- wait measurement

def _age(raw, now: float):
    if not isinstance(raw, str):
        return None
    try:
        return now - datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def job_shard(job_name: str, shards: list[dict]):
    """The shard a job belongs to: its id or its context is part of the job name."""
    low = job_name.lower()
    best = None
    for s in shards:
        for key in (s.get("context"), s.get("id")):
            if isinstance(key, str) and key.strip() and key.lower() in low:
                if best is None or len(key) > best[0]:
                    best = (len(key), s)
    return best[1] if best else None


def waiting_shards(runs: list[dict], shards: list[dict], repo: str | None, now: float,
                   gh_json, is_hosted=None, wait_marker=None, claimed=None) -> list[dict]:
    """Shards that wait for a runner now: [{"shard", "wait_min"}].

    The core measures the wait (`ci_fallback.shard_wait_minutes`): only a `queued` job counts, a run held back
    by the one-at-a-time setting has none, and a shard with any started job has its runner. A job with a
    GitHub-hosted label is the platform's wait and is left out here.

    DL-90 (G6): `wait_marker(shard_id)` gives the `ci-wait` marker of a shard whose job is held for a machine slot, and
    `claimed(shard_id)` says whether a claim exists. A marker without a claim counts as waiting, from its time."""
    base = "repos/%s" % repo if repo else "repos/{owner}/{repo}"
    jobs_of: dict[str, tuple[dict, list[dict], str]] = {}
    for run in runs:
        try:
            data = gh_json(["api", "%s/actions/runs/%s/jobs?per_page=100" % (base, run.get("databaseId"))])
        except Exception:  # noqa: BLE001 - a poll error is retried on the next poll
            continue
        for job in (data.get("jobs", []) if isinstance(data, dict) else []):
            if not isinstance(job, dict):
                continue
            labels = [str(x) for x in job.get("labels") or []]
            if is_hosted and labels and is_hosted(labels):
                continue
            shard = job_shard(str(job.get("name") or ""), shards)
            if shard is not None:
                jobs_of.setdefault(shard["id"], (shard, [], str(run.get("status") or "")))[1].append(job)
    out = []
    for shard, jobs, run_status in jobs_of.values():
        sid = shard["id"]
        marker = wait_marker(sid) if wait_marker else None
        wait = ci_fallback.shard_wait_minutes(jobs, datetime.fromtimestamp(now, timezone.utc), run_status,
                                              wait_marker=marker,
                                              claimed=bool(marker and claimed and claimed(sid)))
        if wait is not None:
            out.append({"shard": shard, "wait_min": wait})
    return out


# ---------------------------------------------------------------- launchers

def http_post(url: str, headers: dict, body: dict) -> int:
    host = urllib.parse.urlparse(url)
    if host.scheme != "https" and not (host.scheme == "http" and host.hostname in ("127.0.0.1", "localhost")):
        raise ValueError("the fire URL must be https (plain http only for 127.0.0.1)")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - scheme checked above
        return resp.status


def session_prompt(sha: str, shard: str, timeout_min) -> str:
    return ("CI fallback for commit %s, shard %s. Do exactly this and nothing else: "
            "git fetch origin && git checkout --detach %s && run the project's setup, then "
            "python scripts/delivery/fallback_run.py --sha %s --shard %s --who cloud --timeout-min %g. "
            "Do not commit, push or open a pull request." % (sha, shard, sha, sha, shard, timeout_min))


def launch_cloud(st: dict, sha: str, shard: dict, post=http_post, env=os.environ) -> None:
    """One session per shard: fire the routine's API trigger with the shard in the text. Raises on failure."""
    cloud = st["cloud"]
    url, token_env = cloud.get("fire_url"), cloud.get("token_env")
    if not isinstance(url, str) or not url or not isinstance(token_env, str) or not token_env:
        raise ValueError("ci.fallback.cloud needs fire_url and token_env")
    token = env.get(token_env, "")
    if not token:
        raise ValueError("the environment variable %s is empty" % token_env)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json",
               "anthropic-beta": "experimental-cc-routine-2026-04-01", "anthropic-version": "2023-06-01",
               "User-Agent": "luismc-delivery-fallback"}
    code = post(url, headers, {"text": session_prompt(sha, shard["id"], st["timeout_min"])})
    if not 200 <= int(code) < 300:
        raise RuntimeError("the routine API answered %s" % code)


def run_gh(args: list[str]):
    return subprocess.run([__import__("shutil").which("gh") or "gh", *args], capture_output=True, text=True, check=False)


def launch_hosted(st: dict, sha: str, shard: dict, repo: str | None, run=run_gh) -> None:
    """Dispatch the hosted-runner workflow for one shard. Raises on failure."""
    wf = st["hosted"].get("workflow") if isinstance(st["hosted"].get("workflow"), str) else "ci-fallback.yml"
    ref = st["hosted"].get("ref") if isinstance(st["hosted"].get("ref"), str) else "main"
    args = ["workflow", "run", wf, "--ref", ref, "-f", "sha=" + sha, "-f", "shard=" + shard["id"],
            "-f", "os=" + str(shard.get("os") or "linux")]
    if repo:
        args += ["--repo", repo]
    proc = run(args)
    if proc.returncode != 0:
        raise RuntimeError("gh workflow run failed: %s" % (proc.stderr or proc.stdout).strip()[:200])


# ---------------------------------------------------------------- the decision

class Deps:
    """Everything with a side effect, so tests can replace it. The defaults are the real ones."""

    def __init__(self, root: str, remote: str = "origin", repo: str | None = None, **over):
        self.root, self.remote, self.repo = root, remote, repo
        self.gh_json = over.get("gh_json") or self._gh_json
        self.now = over.get("now") or time.time
        self.cloud = over.get("cloud") or (lambda st, sha, shard: launch_cloud(st, sha, shard))
        self.hosted = over.get("hosted") or (lambda st, sha, shard: launch_hosted(st, sha, shard, repo))
        self.reserve = over.get("reserve") or (lambda sha, shard: reserve_launch(root, remote, sha, shard))
        self.release = over.get("release") or (lambda sha, shard: release_launch(root, remote, sha, shard))
        self.settled = over.get("settled") or self._settled
        self.cloud_sessions = over.get("cloud_sessions") or (
            lambda: ci_fallback.cloud_ci_sessions(root, remote, datetime.fromtimestamp(self.now(), timezone.utc)))
        self.ready_pr = over.get("ready_pr") or self._ready_pr
        self.wait_marker = over.get("wait_marker") or self._wait_marker
        self.claimed = over.get("claimed") or self._claimed
        self.gate = over.get("gate") or self._gate  # caps: counts the shard before it starts
        self.out = over.get("out") or (lambda line: print(line, flush=True))
        self.state: dict = over.get("state") if over.get("state") is not None else {}
        try:
            import runner_health  # noqa: PLC0415
            self.is_hosted = over.get("is_hosted") or runner_health.is_hosted
        except ImportError:
            self.is_hosted = over.get("is_hosted")

    def _gh_json(self, args):
        proc = run_gh(args)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:200])
        return json.loads(proc.stdout or "null")

    def _settled(self, sha: str, shard: str, prefix: str) -> bool:
        """A claim or a result already exists for this shard."""
        return (remote_has(self.root, self.remote, "%s/%s/%s/*" % (CLAIM_PREFIX, sha, shard))
                or remote_has(self.root, self.remote, "%s/%s/%s" % (prefix, sha, shard)))

    def _wait_marker(self, sha: str, shard: str):
        try:
            return ci_fallback.read_wait(self.root, self.remote, sha, shard)
        except Exception:  # noqa: BLE001 - no marker is the old behaviour
            return None

    def _claimed(self, sha: str, shard: str) -> bool:
        try:
            return ci_fallback.claim_taken(self.root, self.remote, sha, shard)
        except Exception:  # noqa: BLE001
            return False

    def _ready_pr(self, sha: str) -> bool:
        base = "repos/%s" % self.repo if self.repo else "repos/{owner}/{repo}"
        data = self.gh_json(["api", "%s/commits/%s/pulls" % (base, sha)])
        return isinstance(data, list) and any(
            isinstance(p, dict) and p.get("state") == "open" and not p.get("draft") for p in data)

    def _gate(self, st: dict, os_name: str, waited_min: float) -> dict:
        return ci_fallback.fallback_gate(self.root, self.remote, st["cfg"], os_name, waited_min, False,
                                         datetime.fromtimestamp(self.now(), timezone.utc), st["timeout_min"])


def check_and_launch(sha: str, runs: list[dict], deps: Deps, st: dict | None = None,
                     shards: list[dict] | None = None, force: list[dict] | None = None) -> list[dict]:
    """Measure the waits of the pending runs and start the fallback for each shard over X.

    Returns the launches: [{"shard", "kind", "wait_min"}]. Never raises. `force` names shards to launch
    without a wait (the `launch` command); the claim, the caps and the scope rules still apply."""
    try:
        st = st or settings_from(read_config(deps.root))
        if st is None:
            return []
        shards = shards if shards is not None else load_shards(deps.root, st)
        if force is not None:
            waiting = [{"shard": s, "wait_min": float(st["core"]["after_min"])} for s in force]
        else:
            waiting = waiting_shards(runs, shards, deps.repo, deps.now(), deps.gh_json, deps.is_hosted,
                                     wait_marker=lambda sid: deps.wait_marker(sha, sid),
                                     claimed=lambda sid: deps.claimed(sha, sid))
        return _launch(sha, waiting, deps, st, scoped=force is None)
    except Exception as exc:  # noqa: BLE001 - the fallback must never break the watch
        deps.out("ci_watch: fallback skipped (%s: %s)" % (type(exc).__name__, exc))
        return []


def _launch(sha: str, waiting: list[dict], deps: Deps, st: dict, scoped: bool = True) -> list[dict]:
    launched = deps.state.setdefault("launched", set())
    failed = deps.state.setdefault("failed", {})
    warned = deps.state.setdefault("warned", set())
    ready = None
    out = []
    for w in sorted(waiting, key=lambda w: w["shard"]["id"]):
        shard, sid = w["shard"], w["shard"]["id"]
        os_name = str(shard.get("os") or "linux")
        if (sha, sid) in launched or failed.get((sha, sid), 0) >= MAX_LAUNCH_FAILURES:
            continue
        # Under X, or no fallback for this OS: nothing (pure rule of the core, no I/O).
        if not ci_fallback.fallback_decision(st["core"], os_name, w["wait_min"])["start"]:
            continue
        kind = st["core"]["options"][os_name]
        if os_name == "windows" and kind != "github-hosted":
            if (sha, sid, "os") not in warned:
                warned.add((sha, sid, "os"))
                deps.out("ci_watch: WARNING: shard %s is Windows; cloud sessions are Linux, so it has no fallback" % sid)
            continue
        if scoped and os_name == "windows":  # answer 7: hosted Windows on ready pull requests only
            if ready is None:
                ready = bool(deps.ready_pr(sha))
            if not ready:
                continue
        if deps.settled(sha, sid, st["prefix"]):
            launched.add((sha, sid))
            continue
        if kind == "cloud":  # DL-91: never an 11th cloud CI session; wait and retry on the next poll
            limit = ci_fallback.cloud_ci_limit(st["cfg"])
            try:
                busy = int(deps.cloud_sessions()) + deps.state.get("cloud_started", 0)
            except Exception as exc:  # noqa: BLE001 - an unreadable count must not stop the fallback
                busy = 0
                deps.out("ci_watch: could not count cloud CI sessions (%s)" % exc)
            if busy >= limit:
                if (sha, "cloud-limit") not in warned:
                    warned.add((sha, "cloud-limit"))
                    deps.out("ci_watch: %d cloud CI sessions run (limit %d); shard %s waits" % (busy, limit, sid))
                continue
        if not deps.reserve(sha, sid):
            launched.add((sha, sid))  # someone else reserved it (or git refused): not ours to start
            continue
        gate = deps.gate(st, os_name, w["wait_min"])  # counts the caps before anything starts
        if not gate.get("start"):
            deps.release(sha, sid)  # the launch stays possible when the cap lifts
            if gate.get("warning") and (sha, kind) not in warned:
                warned.add((sha, kind))
                deps.out("ci_watch: %s" % gate["warning"])
            continue
        try:
            (deps.cloud if kind == "cloud" else deps.hosted)(st, sha, shard)
        except Exception as exc:  # noqa: BLE001
            failed[(sha, sid)] = failed.get((sha, sid), 0) + 1
            deps.release(sha, sid)
            deps.out("ci_watch: WARNING: fallback launch (%s) failed for shard %s: %s" % (kind, sid, exc))
            continue
        launched.add((sha, sid))
        if kind == "cloud":
            deps.state["cloud_started"] = deps.state.get("cloud_started", 0) + 1
        deps.out("ci_watch: fallback (%s) started for shard %s after %d min of waiting"
                 % (kind, sid, int(w["wait_min"])))
        out.append({"shard": sid, "kind": kind, "wait_min": w["wait_min"]})
    return out


# ---------------------------------------------------------------- CLI

def sweep(deps: Deps) -> int:
    """The hourly routine: every pending run on the repository, grouped by commit."""
    st = settings_from(read_config(deps.root))
    if st is None:
        print("fallback_launch: no ci.fallback in .delivery/config.json: nothing to do")
        return 0
    by_sha: dict[str, list[dict]] = {}
    for status in ("queued", "in_progress"):
        args = ["run", "list", "--status", status, "--limit", "100", "--json", "databaseId,headSha,workflowName"]
        if deps.repo:
            args += ["--repo", deps.repo]
        try:
            for run in deps.gh_json(args) or []:
                by_sha.setdefault(str(run.get("headSha")), []).append(run)
        except Exception as exc:  # noqa: BLE001
            print("fallback_launch: could not list the %s runs (%s)" % (status, exc), file=sys.stderr)
            return 2
    started = 0
    for sha, runs in sorted(by_sha.items()):
        started += len(check_and_launch(sha, runs, deps, st))
    print("fallback_launch: swept %d commit(s), started %d shard(s)" % (len(by_sha), started))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fallback_launch.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["sweep", "launch"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--repo")
    ap.add_argument("--sha")
    ap.add_argument("--shard")
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("--dry-run", action="store_true", help="sweep: say what would start, start nothing")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    over = {}
    if args.dry_run:
        over.update(cloud=lambda st, sha, sh: None, hosted=lambda st, sha, sh: None,
                    reserve=lambda sha, sh: True)
    deps = Deps(root, args.remote, args.repo, **over)
    if args.action == "sweep":
        return sweep(deps)
    st = settings_from(read_config(root))
    if st is None:
        print("fallback_launch: no ci.fallback in .delivery/config.json", file=sys.stderr)
        return 2
    if not args.sha or not FULL_SHA.fullmatch(args.sha.lower()) or not args.shard:
        print("fallback_launch: launch needs --sha (40 characters) and --shard", file=sys.stderr)
        return 2
    shard = next((s for s in load_shards(root, st) if s["id"] == args.shard), None)
    if shard is None:
        print("fallback_launch: no shard %r in the shard table" % args.shard, file=sys.stderr)
        return 2
    if args.kind:  # a by-hand launch may pick the kind for this one shard
        st = dict(st, core=dict(st["core"], options=dict(st["core"]["options"], **{str(shard.get("os") or "linux"): args.kind})))
    done = check_and_launch(args.sha.lower(), [], deps, st, [shard], force=[shard])
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
