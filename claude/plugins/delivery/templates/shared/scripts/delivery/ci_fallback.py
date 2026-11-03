#!/usr/bin/env python3
"""CI Option 4 core (CIR10 S7): own runners first, a fallback after a wait, one result per shard. SKELETON (DL23).

The module is the interface DL24 (fallback launchers) builds on. Every public function below is final in name,
arguments and return shape; the bodies are filled in by the next commits. Standard library only. Plain git for
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
    next_attempt(root, remote, sha, shard, cap=2)   -> int | None
    post_checked(root, remote, repo, token, result, sha, shard, attempt, holder) -> dict
    reap(root, remote, repo, token, sha, shard, context, timeout_min, now=None, cap=2) -> dict
    reserve(root, remote, settings, now, kind, est_minutes=0) -> dict
    settle(root, remote, settings, now, kind, reserved_minutes, actual_minutes) -> None
    fallback_gate(root, remote, cfg, os_name, waited_min, offline, now, timeout_min) -> dict
Exit codes of the CLI: 0 done, 1 refused, 2 error, 3 claim lost (not an error: end without work).
"""
from __future__ import annotations

import sys

CLAIM_PREFIX = "ci-claim"
POSTED_PREFIX = "ci-posted"
DEFAULT_RECORDS_BRANCH = "ci-pass-records"
COUNTER_FILE = "fallback-counter.json"
ATTEMPT_CAP = 2


def fallback_settings(cfg: dict) -> dict:
    """Read `ci.fallback` from a parsed config. Returns {"options": {os: "cloud"|"github-hosted"}, "after_min":
    float|None, "after_min_if_offline": float|None (None = same as after_min), "only_for": "all",
    "max_shards_per_day": int|None, "max_minutes_per_month": int|None, "records_branch": str, "enabled": bool}.
    `enabled` is False when after_min is absent or no OS has a fallback. Bad values are dropped, never guessed."""
    raise NotImplementedError


def shard_wait_minutes(jobs: list, now, run_status: str = ""):
    """Minutes the shard has waited for a RUNNER, or None when it is not waiting (answer 5). `jobs` are the
    Actions job dicts of one shard (status, created_at, started_at). A job counts only while status is `queued`
    and started_at is empty. A run in status pending/waiting (the CI_SERIAL queue) or with no jobs yet returns
    None. If any job of the shard has started, the shard has a runner: None. Otherwise the oldest wait."""
    raise NotImplementedError


def fallback_decision(settings: dict, os_name: str, waited_min, offline: bool = False) -> dict:
    """Pure rule, no I/O. Returns {"start": bool, "kind": "cloud"|"github-hosted"|None, "reason": str}. Start only
    when the fallback is enabled, this OS has one, and waited_min >= after_min (or >= after_min_if_offline when
    `offline`, no online runner carries the labels). Caps are not looked at here: see fallback_gate."""
    raise NotImplementedError


def claim_ref(sha: str, shard: str, attempt: int) -> str:
    """The branch name of a claim: ci-claim/<sha>/<shard>/<attempt>."""
    raise NotImplementedError


def claim(root: str, remote: str, sha: str, shard: str, attempt: int, holder: str, now=None) -> bool:
    """Try to take the shard. True = this caller holds it. False = somebody else does (end at once, no work, no
    status). Atomic: a push that creates the claim branch; git refuses a second create. Never pre-empts."""
    raise NotImplementedError


def read_claim(root: str, remote: str, sha: str, shard: str, attempt: int):
    """{"holder", "sha", "shard", "attempt", "at"} of an existing claim, or None."""
    raise NotImplementedError


def next_attempt(root: str, remote: str, sha: str, shard: str, cap: int = ATTEMPT_CAP):
    """The attempt number to claim now: 1 when nothing is claimed, the live attempt while one is held and not yet
    answered, N+1 after attempt N has a posted marker with state error from the reaper. None when the cap is
    spent (no attempt is left)."""
    raise NotImplementedError


def post_checked(root: str, remote: str, repo: str, token: str, result: dict, sha: str, shard: str,
                 attempt: int, holder: str) -> dict:
    """Post ONE commit status for the shard, only if all hold: the result is for `sha`; the claim of
    (sha, shard, attempt) names `holder`; no newer attempt exists; nobody posted this attempt yet (the
    ci-posted marker is created first, atomically). Returns {"posted": bool, "reason": str, "context": str,
    "state": str}. Refusal posts nothing. A failed API call removes the marker so the same holder can retry."""
    raise NotImplementedError


def reap(root: str, remote: str, repo: str, token: str, sha: str, shard: str, context: str,
         timeout_min: float, now=None, cap: int = ATTEMPT_CAP) -> dict:
    """The reaper, run by the watcher. A claim with no posted marker older than `timeout_min` is dead: post
    state `error` ("run lost") for it through the same marker, and open attempt N+1 unless N is at the cap.
    Returns {"action": "none"|"reaped"|"reaped-final", "attempt": int, "next_attempt": int|None}."""
    raise NotImplementedError


def reserve(root: str, remote: str, settings: dict, now, kind: str, est_minutes: float = 0) -> dict:
    """Count one fallback shard (and est_minutes for kind github-hosted) on the records branch BEFORE it starts.
    Returns {"ok": True} or {"ok": False, "warning": "fallback paused: daily cap" | "fallback paused: monthly
    cap"}. Never lets a counter pass its cap, also with two callers at once (push, retry on a lost race)."""
    raise NotImplementedError


def settle(root: str, remote: str, settings: dict, now, kind: str, reserved_minutes: float,
           actual_minutes: float) -> None:
    """After the shard: replace the reserved minutes by the real ones (never below zero)."""
    raise NotImplementedError


def fallback_gate(root: str, remote: str, cfg: dict, os_name: str, waited_min, offline: bool, now,
                  timeout_min: float) -> dict:
    """What the watcher calls once per waiting shard. Combines fallback_decision and reserve. Returns {"start":
    bool, "kind": ..., "reason": str, "warning": str|None, "reserved_minutes": float}. On start=True the caps
    are already counted: DL24 launches the fallback (which then claims LAST, just before the first test)."""
    raise NotImplementedError


def main(argv=None) -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
