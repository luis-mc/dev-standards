#!/usr/bin/env python3
"""CI Option 4 core (CIR10 S7): own runners first, a fallback after a wait, one result per shard. (DL23).

The module is the interface DL24 (fallback launchers) builds on. Standard library only. Plain git for
every shared marker, no service. Contract: docs/proposals/CIR10-delivery-ci.md section 4 and the owner answers in
section 8 (2 statuses, 4 optional caps, 5 only runner waits count, 6 every run, 9 first claim wins).

Config (`.delivery/config.json`):
    "ci": {"fallback": {
        "options": {"linux": "cloud", "windows": "github-hosted"},   # which fallback per OS
        "after_min": 10,                  # X. No default: absent means the fallback is off
        "after_min_if_offline": 2,        # optional; absent means "same as X"
        "only_for": "all",                # answer 6: every run
        "max_shards_per_day": 20,         # optional cap (answer 4)
        "max_minutes_per_month": 600,     # optional cap, hosted runners only
        "records_branch": "ci-pass-records"}}

Markers (branches on the remote, created by a push that creates them; a second create is refused by git):
    ci-claim/<sha>/<shard>/<attempt>    who runs the shard (first claim wins, nobody is pre-empted)
    ci-posted/<sha>/<shard>/<attempt>   who posted the one status of that attempt (never two)
Counters live in `fallback-counter.json` on the records branch.

Public functions (all return plain dicts, lists, bools or None; none prints):
    fallback_settings(cfg)                          -> dict
    shard_wait_minutes(jobs, now, run_status="")    -> float | None
    fallback_decision(settings, os_name, waited_min, offline=False) -> dict
    claim_ref(sha, shard, attempt)                  -> str
    claim(root, remote, sha, shard, attempt, holder, now=None) -> bool
    read_claim(root, remote, sha, shard, attempt)   -> dict | None
    next_attempt(root, remote, sha, shard, cap=2)   -> int | None   (None: answered already, or cap spent)
    post_checked(root, remote, repo, token, result, sha, shard, attempt, holder) -> dict
    reap(root, remote, repo, token, sha, shard, context, timeout_min, now=None, cap=2, results_prefix="ci-result") -> dict
    reserve(root, remote, settings, now, kind, est_minutes=0) -> dict
    settle(root, remote, settings, now, kind, reserved_minutes, actual_minutes) -> None
    fallback_gate(root, remote, cfg, os_name, waited_min, offline, now, timeout_min) -> dict
Exit codes of the CLI: 0 done, 1 refused, 2 error, 3 claim lost (not an error: end without work).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud_status as CS  # noqa: E402  (post_status, status_payload, token_from, cloud_settings, read_config)

CLAIM_PREFIX = "ci-claim"
POSTED_PREFIX = "ci-posted"
DEFAULT_RECORDS_BRANCH = "ci-pass-records"
COUNTER_FILE = "fallback-counter.json"
ATTEMPT_CAP = 2
KINDS = ("cloud", "github-hosted")
OSES = ("linux", "windows", "macos")
EMPTY_TREE_ENV = {"GIT_AUTHOR_NAME": "ci-fallback", "GIT_AUTHOR_EMAIL": "ci-fallback@localhost",
                  "GIT_COMMITTER_NAME": "ci-fallback", "GIT_COMMITTER_EMAIL": "ci-fallback@localhost"}
PUSH_RETRIES = 8


# --- small helpers ------------------------------------------------------------------------------------------

def _git(root, *args, stdin=None):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, input=stdin, check=False,
                          env={**os.environ, **EMPTY_TREE_ENV})


def _num(v, minimum=0):
    """A real number >= minimum, or None. Booleans are not numbers."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < minimum:
        return None
    return v


def _now(now):
    return now if isinstance(now, datetime) else datetime.now(timezone.utc)


def _iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _marker_commit(root, payload: dict):
    """A commit on the empty tree whose message is the JSON payload (and a nonce, so two callers never push the
    same commit: an identical commit would count as 'already there' and both would think they won)."""
    tree = _git(root, "mktree", stdin="")
    if tree.returncode:
        raise RuntimeError("git mktree failed: " + tree.stderr.strip())
    body = json.dumps({**payload, "nonce": "%d-%06d" % (time.time_ns(), random.randrange(10**6))}, sort_keys=True)
    c = _git(root, "commit-tree", tree.stdout.strip(), "-m", body)
    if c.returncode:
        raise RuntimeError("git commit-tree failed: " + c.stderr.strip())
    return c.stdout.strip()


def _create_branch(root, remote, branch, payload) -> bool:
    """Create `branch` on the remote. True only for the caller whose push created it."""
    commit = _marker_commit(root, payload)
    ref = "refs/heads/" + branch
    r = _git(root, "push", "-q", remote, "%s:%s" % (commit, ref), "--force-with-lease=%s:" % ref)
    return r.returncode == 0


def _delete_branch(root, remote, branch):
    _git(root, "push", "-q", remote, ":refs/heads/" + branch)


def _ls(root, remote, pattern) -> list:
    r = _git(root, "ls-remote", "--heads", remote, "refs/heads/" + pattern)
    if r.returncode:
        raise RuntimeError("git ls-remote failed: " + r.stderr.strip())
    return [ln.partition("\t")[2][len("refs/heads/"):] for ln in r.stdout.splitlines() if "\t" in ln]


def _read_branch(root, remote, branch):
    """The JSON in the message of the tip commit of `branch`, or None."""
    local = "refs/ci-fetched/" + branch
    if _git(root, "fetch", "-q", remote, "+refs/heads/%s:%s" % (branch, local)).returncode:
        return None
    shown = _git(root, "log", "-1", "--format=%B", local)
    try:
        data = json.loads(shown.stdout)
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _attempts(root, remote, sha, shard) -> list:
    out = []
    for name in _ls(root, remote, "%s/%s/%s/*" % (CLAIM_PREFIX, sha, shard)):
        tail = name.rsplit("/", 1)[-1]
        if tail.isdigit():
            out.append(int(tail))
    return sorted(out)


def _posted_ref(sha, shard, attempt):
    return "%s/%s/%s/%d" % (POSTED_PREFIX, sha, shard, attempt)


# --- config ---------------------------------------------------------------------------------------------------

def fallback_settings(cfg: dict) -> dict:
    """Read `ci.fallback` from a parsed config. Returns {"options": {os: "cloud"|"github-hosted"}, "after_min":
    float|None, "after_min_if_offline": float|None (None = same as after_min), "only_for": "all",
    "max_shards_per_day": int|None, "max_minutes_per_month": int|None, "records_branch": str, "enabled": bool}.
    `enabled` is False when after_min is absent or no OS has a fallback. Bad values are dropped, never guessed."""
    ci = cfg.get("ci") if isinstance(cfg, dict) and isinstance(cfg.get("ci"), dict) else {}
    fb = ci.get("fallback") if isinstance(ci.get("fallback"), dict) else {}
    raw = fb.get("options") if isinstance(fb.get("options"), dict) else {}
    options = {k: v for k, v in raw.items() if k in OSES and v in KINDS}
    after = _num(fb.get("after_min"), 0)
    offline = _num(fb.get("after_min_if_offline"), 0)
    day, month = _num(fb.get("max_shards_per_day"), 0), _num(fb.get("max_minutes_per_month"), 0)
    rb = fb.get("records_branch")
    return {"options": options, "after_min": after, "after_min_if_offline": offline,
            "only_for": "all",  # answer 6: every run may use the fallback
            "max_shards_per_day": int(day) if day is not None else None,
            "max_minutes_per_month": month, "records_branch": rb if isinstance(rb, str) and rb.strip() else DEFAULT_RECORDS_BRANCH,
            "enabled": after is not None and bool(options)}


# --- wait and decision -----------------------------------------------------------------------------------------

def shard_wait_minutes(jobs: list, now, run_status: str = ""):
    """Minutes the shard has waited for a RUNNER, or None when it is not waiting (answer 5). `jobs` are the
    Actions job dicts of one shard (status, created_at, started_at). A job counts only while status is `queued`
    and started_at is empty. A run in status pending/waiting (the CI_SERIAL queue) or with no jobs yet returns
    None. If any job of the shard has started, the shard has a runner: None. Otherwise the oldest wait."""
    if run_status in ("pending", "waiting", "requested") or not jobs:
        return None
    now = _utc(_now(now))
    waits = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        if j.get("started_at") or j.get("status") in ("in_progress", "completed"):
            return None
        if j.get("status") == "queued":
            created = _parse(j.get("created_at"))
            if created is not None:
                waits.append(max(0.0, (now - _utc(created)).total_seconds() / 60.0))
    return max(waits) if waits else None


def fallback_decision(settings: dict, os_name: str, waited_min, offline: bool = False) -> dict:
    """Pure rule, no I/O. Returns {"start": bool, "kind": "cloud"|"github-hosted"|None, "reason": str}. Start only
    when the fallback is enabled, this OS has one, and waited_min >= after_min (or >= after_min_if_offline when
    `offline`, no online runner carries the labels). Caps are not looked at here: see fallback_gate."""
    def no(reason):
        return {"start": False, "kind": None, "reason": reason}
    if not settings.get("enabled"):
        return no("fallback is off (no after_min or no fallback for any OS)")
    kind = settings["options"].get(os_name)
    if kind is None:
        return no("no fallback for %s" % os_name)
    if waited_min is None:
        return no("the shard is not waiting for a runner")
    limit = settings["after_min"]
    if offline and settings.get("after_min_if_offline") is not None:
        limit = settings["after_min_if_offline"]
    if waited_min < limit:
        return no("waited %.1f of %.1f min" % (waited_min, limit))
    return {"start": True, "kind": kind, "reason": "waited %.1f min, limit %.1f%s" % (
        waited_min, limit, " (no online runner)" if offline else "")}


# --- the claim ----------------------------------------------------------------------------------------------------

def claim_ref(sha: str, shard: str, attempt: int) -> str:
    """The branch name of a claim: ci-claim/<sha>/<shard>/<attempt>."""
    return "%s/%s/%s/%d" % (CLAIM_PREFIX, sha, shard, int(attempt))


def claim(root: str, remote: str, sha: str, shard: str, attempt: int, holder: str, now=None) -> bool:
    """Try to take the shard. True = this caller holds it. False = somebody else does (end at once, no work, no
    status). Atomic: a push that creates the claim branch; git refuses a second create. Never pre-empts."""
    if attempt < 1 or attempt > ATTEMPT_CAP:
        return False
    return _create_branch(root, remote, claim_ref(sha, shard, attempt), {
        "holder": holder, "sha": sha, "shard": shard, "attempt": int(attempt), "at": _iso(_now(now))})


def read_claim(root: str, remote: str, sha: str, shard: str, attempt: int):
    """{"holder", "sha", "shard", "attempt", "at"} of an existing claim, or None."""
    return _read_branch(root, remote, claim_ref(sha, shard, attempt))


def next_attempt(root: str, remote: str, sha: str, shard: str, cap: int = ATTEMPT_CAP):
    """The attempt number to claim now: 1 when nothing is claimed, the live attempt while one is held and not yet
    answered (the claim then fails), N+1 after the reaper answered attempt N with `error`. None when nothing is
    left to claim: the shard has its answer, or the cap is spent."""
    done = _attempts(root, remote, sha, shard)
    if not done:
        return 1
    top = done[-1]
    posted = _read_branch(root, remote, _posted_ref(sha, shard, top))
    if posted is None:
        return top
    if posted.get("reaped") and top < cap:
        return top + 1
    return None


# --- the status poster and the reaper --------------------------------------------------------------------------------

def _refuse(reason, context="", state=""):
    return {"posted": False, "reason": reason, "context": context, "state": state}


def _post_once(root, remote, repo, token, sha, shard, attempt, holder, body, reaped):
    """Create the posted marker, then the status. The marker is what makes it one post per attempt."""
    marker = _posted_ref(sha, shard, attempt)
    if not _create_branch(root, remote, marker, {"holder": holder, "state": body["state"], "reaped": bool(reaped),
                                                  "context": body["context"], "sha": sha}):
        return _refuse("attempt %d of %s already has its status" % (attempt, shard), body["context"], body["state"])
    try:
        CS.post_status(repo, sha, body, token)
    except Exception as exc:  # noqa: BLE001 - any API failure frees the marker so the poster can retry
        _delete_branch(root, remote, marker)
        return {**_refuse("status not posted: %s" % exc, body["context"], body["state"]), "error": True}
    return {"posted": True, "reason": "posted", "context": body["context"], "state": body["state"]}


def post_checked(root: str, remote: str, repo: str, token: str, result: dict, sha: str, shard: str,
                 attempt: int, holder: str) -> dict:
    """Post ONE commit status for the shard, only if all hold: the result is for `sha`; the claim of
    (sha, shard, attempt) names `holder`; no newer attempt exists; nobody posted this attempt yet (the
    ci-posted marker is created first, atomically). Returns {"posted": bool, "reason": str, "context": str,
    "state": str}. Refusal posts nothing. A failed API call removes the marker so the same holder can retry."""
    try:
        full, body = CS.status_payload(result, sha)
    except ValueError as exc:
        return _refuse(str(exc))
    if result.get("shard") not in (None, shard):
        return _refuse("the result is for shard %s, not %s" % (result.get("shard"), shard), body["context"])
    held = read_claim(root, remote, full, shard, attempt)
    if held is None:
        return _refuse("no claim for %s attempt %d: nothing is posted" % (shard, attempt), body["context"])
    if held.get("holder") != holder:
        return _refuse("the claim is held by %s, not %s" % (held.get("holder"), holder), body["context"])
    if any(a > attempt for a in _attempts(root, remote, full, shard)):
        return _refuse("attempt %d is superseded by a newer one" % attempt, body["context"])
    return _post_once(root, remote, repo, token, full, shard, attempt, holder, body, reaped=False)


def reap(root: str, remote: str, repo: str, token: str, sha: str, shard: str, context: str,
         timeout_min: float, now=None, cap: int = ATTEMPT_CAP, results_prefix: str = "ci-result") -> dict:
    """The reaper, run by the watcher. A claim with no posted marker older than `timeout_min` is dead: post
    state `error` ("run lost") for it through the same marker, and open attempt N+1 unless N is at the cap.
    A pushed result branch `<results_prefix>/<sha>/<shard>` counts as a result (the cloud path posts it).
    Returns {"action": "none"|"reaped"|"reaped-final", "attempt": int|None, "next_attempt": int|None}."""
    none = {"action": "none", "attempt": None, "next_attempt": None}
    done = _attempts(root, remote, sha, shard)
    if not done:
        return none
    top = done[-1]
    if _read_branch(root, remote, _posted_ref(sha, shard, top)) is not None:
        return {**none, "attempt": top}
    if _ls(root, remote, "%s/%s/%s" % (results_prefix, sha, shard)):
        return {**none, "attempt": top}
    held = read_claim(root, remote, sha, shard, top) or {}
    at = _parse(held.get("at"))
    if at is None or (_utc(_now(now)) - _utc(at)).total_seconds() / 60.0 < timeout_min:
        return {**none, "attempt": top}
    body = {"state": "error", "context": context, "description": "run lost (attempt %d, no result in %g min)" % (top, timeout_min)}
    res = _post_once(root, remote, repo, token, sha, shard, top, "reaper", body, reaped=True)
    if not res["posted"]:
        return {**none, "attempt": top}
    nxt = top + 1 if top < cap else None
    return {"action": "reaped" if nxt else "reaped-final", "attempt": top, "next_attempt": nxt}


# --- caps --------------------------------------------------------------------------------------------------------------

def _counter_read(root, remote, branch):
    """(counter dict, tip sha or None)."""
    local = "refs/ci-fetched/" + branch
    if _git(root, "fetch", "-q", remote, "+refs/heads/%s:%s" % (branch, local)).returncode:
        return {"days": {}, "months": {}}, None
    tip = _git(root, "rev-parse", local).stdout.strip()
    shown = _git(root, "show", "%s:%s" % (local, COUNTER_FILE))
    try:
        data = json.loads(shown.stdout)
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    return {"days": data.get("days") if isinstance(data.get("days"), dict) else {},
            "months": data.get("months") if isinstance(data.get("months"), dict) else {}}, tip


def _counter_push(root, remote, branch, data, tip) -> bool:
    blob = _git(root, "hash-object", "-w", "--stdin", stdin=json.dumps(data, sort_keys=True, indent=1) + "\n")
    tree = _git(root, "mktree", stdin="100644 blob %s\t%s\n" % (blob.stdout.strip(), COUNTER_FILE))
    # the nonce keeps two callers from making the same commit: an identical commit pushes as "up to date" for both
    args = ["commit-tree", tree.stdout.strip(), "-m", "fallback counter %d-%06d" % (time.time_ns(), random.randrange(10**6))] + (["-p", tip] if tip else [])
    commit = _git(root, *args).stdout.strip()
    ref = "refs/heads/" + branch
    push = ["push", "-q", remote, "%s:%s" % (commit, ref)]
    if tip is None:
        push.append("--force-with-lease=%s:" % ref)
    return _git(root, *push).returncode == 0


def _counter_update(root, remote, settings, now, change):
    """Read, let `change(counter, day, month)` edit or refuse, push; retry when another caller pushed first.
    `change` returns None to write, or a warning string to stop. Returns None or the warning."""
    now = _utc(_now(now))
    day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    for _ in range(PUSH_RETRIES):
        data, tip = _counter_read(root, remote, settings["records_branch"])
        data["days"] = {day: data["days"].get(day, 0)}
        data["months"] = {month: data["months"].get(month, {"shards": 0, "minutes": 0})}
        warn = change(data, day, month)
        if warn:
            return warn
        if _counter_push(root, remote, settings["records_branch"], data, tip):
            return None
        time.sleep(random.random() * 0.1)
    return "fallback paused: counter busy"


def reserve(root: str, remote: str, settings: dict, now, kind: str, est_minutes: float = 0) -> dict:
    """Count one fallback shard (and est_minutes for kind github-hosted) on the records branch BEFORE it starts.
    Returns {"ok": True} or {"ok": False, "warning": "fallback paused: daily cap" | "fallback paused: monthly
    cap"}. Never lets a counter pass its cap, also with two callers at once (push, retry on a lost race)."""
    minutes = est_minutes if kind == "github-hosted" else 0

    def change(data, day, month):
        cap_d, cap_m = settings.get("max_shards_per_day"), settings.get("max_minutes_per_month")
        if cap_d is not None and data["days"][day] + 1 > cap_d:
            return "fallback paused: daily cap"
        if kind == "github-hosted" and cap_m is not None and data["months"][month]["minutes"] + minutes > cap_m:
            return "fallback paused: monthly cap"
        data["days"][day] += 1
        data["months"][month]["shards"] += 1
        data["months"][month]["minutes"] += minutes
        return None
    warn = _counter_update(root, remote, settings, now, change)
    return {"ok": True} if warn is None else {"ok": False, "warning": warn}


def settle(root: str, remote: str, settings: dict, now, kind: str, reserved_minutes: float,
           actual_minutes: float) -> None:
    """After the shard: replace the reserved minutes by the real ones (never below zero)."""
    if kind != "github-hosted":
        return

    def change(data, day, month):
        m = data["months"][month]
        m["minutes"] = max(0, m["minutes"] - reserved_minutes + actual_minutes)
        return None
    _counter_update(root, remote, settings, now, change)


def fallback_gate(root: str, remote: str, cfg: dict, os_name: str, waited_min, offline: bool, now,
                  timeout_min: float) -> dict:
    """What the watcher calls once per waiting shard. Combines fallback_decision and reserve. Returns {"start":
    bool, "kind": ..., "reason": str, "warning": str|None, "reserved_minutes": float}. On start=True the caps
    are already counted: DL24 launches the fallback (which then claims LAST, just before the first test)."""
    settings = fallback_settings(cfg)
    d = fallback_decision(settings, os_name, waited_min, offline)
    out = {"start": False, "kind": d["kind"], "reason": d["reason"], "warning": None, "reserved_minutes": 0}
    if not d["start"]:
        return out
    est = timeout_min if d["kind"] == "github-hosted" else 0
    r = reserve(root, remote, settings, now, d["kind"], est)
    if not r["ok"]:
        return {**out, "kind": None, "reason": "cap reached", "warning": r["warning"]}
    return {**out, "start": True, "reserved_minutes": est}


# --- command line -----------------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ci_fallback.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["claim", "post", "reap", "gate"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--sha")
    ap.add_argument("--shard")
    ap.add_argument("--attempt", type=int)
    ap.add_argument("--holder")
    ap.add_argument("--result")
    ap.add_argument("--context")
    ap.add_argument("--os", dest="os_name")
    ap.add_argument("--waited", type=float)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--timeout-min", type=float)
    ap.add_argument("--repo")
    ap.add_argument("--token-env")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    cfg = CS.read_config(root)
    st = CS.cloud_settings(cfg)
    try:
        if a.action == "gate":
            if not a.os_name:
                print("ci_fallback: gate needs --os", file=sys.stderr)
                return 2
            tmo = a.timeout_min if a.timeout_min else 60.0
            print(json.dumps(fallback_gate(root, a.remote, cfg, a.os_name, a.waited, a.offline, None, tmo)))
            return 0
        if not (a.sha and a.shard):
            print("ci_fallback: %s needs --sha and --shard" % a.action, file=sys.stderr)
            return 2
        if a.action == "claim":
            if not a.holder:
                print("ci_fallback: claim needs --holder", file=sys.stderr)
                return 2
            n = a.attempt or next_attempt(root, a.remote, a.sha, a.shard)
            if n is None or not claim(root, a.remote, a.sha, a.shard, n, a.holder):
                print("ci_fallback: claim lost: end without work and post nothing")
                return 3
            print(json.dumps({"claimed": True, "attempt": n}))
            return 0
        repo, env_name = a.repo or st["repo"], a.token_env or st["token_env"]
        token = CS.token_from(env_name)
        if a.action == "post":
            if not (a.result and a.attempt and a.holder):
                print("ci_fallback: post needs --result, --attempt and --holder", file=sys.stderr)
                return 2
            with open(a.result, encoding="utf-8") as f:
                res = post_checked(root, a.remote, repo, token, json.load(f), a.sha, a.shard, a.attempt, a.holder)
            print(json.dumps(res))
            return 0 if res["posted"] else (2 if res.get("error") else 1)
        if not a.context:
            print("ci_fallback: reap needs --context", file=sys.stderr)
            return 2
        tmo = a.timeout_min if a.timeout_min else float(st["shard_timeout_min"] if "shard_timeout_min" in st else 60)
        print(json.dumps(reap(root, a.remote, repo, token, a.sha, a.shard, a.context, tmo)))
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print("ci_fallback: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
