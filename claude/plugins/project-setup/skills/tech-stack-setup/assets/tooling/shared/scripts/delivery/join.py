#!/usr/bin/env python3
"""Join gated branches into the integration branch (STACKSPEC 13.6).

    join.py --into INTEGRATION BRANCH [BRANCH ...] [--no-gate] [--push] [--remote origin]

Fetches, checks out INTEGRATION at its remote head, and for each BRANCH in order:
requires a trusted, passing gate result (a base older than INTEGRATION's head is
fine), then merges it with `git merge --no-ff -m "Join BRANCH"`. A conflict that
touches only a lockfile is resolved by taking INTEGRATION's version and re-running
gate.json's `setup`; any other conflict aborts that merge, writes
.delivery/join-result.json and exits 3. After the last merge the branch gate runs
on the joined head (unless --no-gate); --push then pushes INTEGRATION and its result.

Exit: 0 joined, 1 a result is not trusted or the gate/push failed, 2 usage or
configuration error (or no result), 3 stopped at a conflict.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import delivery_common as dc
import gate_verify


def write_join_result(root: Path, joined: list[str], stopped_at: str | None, conflicts: list[str], reason: str | None = None) -> None:
    data: dict = {"joined": joined, "stopped_at": stopped_at, "conflicts": conflicts}
    if reason:
        data["reason"] = reason
    dc.write_json(root / dc.JOIN_RESULT_PATH, data)


def merge_in_progress(root: Path) -> bool:
    return dc.run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=root, check=False).returncode == 0


def abort_merge(root: Path) -> None:
    if merge_in_progress(root):
        dc.run_git(["merge", "--abort"], cwd=root, check=False)


def unmerged(root: Path) -> list[str]:
    out = dc.git(["diff", "--name-only", "--diff-filter=U", "-z"], cwd=root, check=False)
    return sorted(p for p in out.split("\0") if p)


def resolve_lockfiles(root: Path, cfg: dict, branch: str, lock: list[str]) -> str | None:
    """Take INTEGRATION's lockfiles and re-run setup. Returns None on success,
    else why it could not."""
    for path in lock:
        if dc.run_git(["checkout", "--ours", "--", path], cwd=root, check=False).returncode != 0:
            return "no integration version of %s to take" % path
        dc.run_git(["add", "--", path], cwd=root)
    for cmd in cfg["setup"]:
        print("==> setup after lockfile resolution\n    $ %s" % cmd, flush=True)
        code, _ = dc.run_command(cmd, root)
        if code != 0:
            return "setup failed (exit %d): %s" % (code, cmd)
    for path in lock:  # setup may have regenerated the lockfile
        dc.run_git(["add", "--", path], cwd=root)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="join.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--into", required=True, metavar="INTEGRATION", help="integration branch")
    ap.add_argument("branches", nargs="+", metavar="BRANCH", help="branches to join, in order")
    ap.add_argument("--no-gate", action="store_true", help="skip the branch gate on the joined head")
    ap.add_argument("--push", action="store_true", help="push INTEGRATION (and its gate result) when done")
    ap.add_argument("--remote", default="origin")
    args = ap.parse_args(argv)

    root = dc.repo_root()
    cfg = dc.load_gate(root)
    dirty = dc.dirty_paths(root)
    if dirty:
        dc.eprint("error: working tree is not clean; commit or stash first:")
        for p in dirty[:10]:
            dc.eprint("    " + p)
        return dc.EXIT_USAGE
    if merge_in_progress(root):
        raise dc.DeliveryError("a merge is already in progress; finish or abort it first")

    remote, into = args.remote, args.into
    dc.git(["fetch", "--quiet", remote], cwd=root)
    integ_ref = "%s/%s" % (remote, into)
    if dc.rev(integ_ref, root) is None:
        raise dc.DeliveryError("integration branch '%s' not found on remote '%s'" % (into, remote))
    dc.git(["checkout", "--quiet", "-B", into, integ_ref], cwd=root)
    print("join: %s at %s" % (into, dc.rev("HEAD", root)[:10]))

    joined: list[str] = []
    for branch in args.branches:
        verdict = gate_verify.verify(branch, integ_ref, remote, allow_older_base=True, root=root)
        if not verdict["trusted"]:
            dc.eprint("join: %s has no trusted passing gate result:" % branch)
            for reason in verdict["reasons"]:
                dc.eprint("  - " + reason)
            write_join_result(root, joined, branch, [], "; ".join(verdict["reasons"]))
            return verdict["exit"]

        print("join: merging %s" % branch, flush=True)
        merge = dc.run_git(
            ["merge", "--no-ff", "-m", "Join %s" % branch, "%s/%s" % (remote, branch)],
            cwd=root,
            check=False,
            env=dc.git_env(),
        )
        if merge.returncode == 0:
            print(merge.stdout.strip())
            joined.append(branch)
            continue

        conflicts = unmerged(root)
        if not conflicts:
            abort_merge(root)
            dc.eprint("join: git merge failed for %s: %s" % (branch, (merge.stderr or merge.stdout).strip()))
            write_join_result(root, joined, branch, [], "merge failed")
            return dc.EXIT_USAGE

        lock = [c for c in conflicts if dc.is_lockfile(c, cfg)]
        if len(lock) == len(conflicts):
            print("join: %s conflicts only in %s; taking %s's version and re-running setup" % (branch, ", ".join(lock), into))
            problem = resolve_lockfiles(root, cfg, branch, lock)
            if problem is not None:
                abort_merge(root)
                dc.eprint("join: could not resolve the lockfile conflict: %s" % problem)
                write_join_result(root, joined, branch, conflicts, problem)
                return dc.EXIT_CONFLICT
            commit = dc.run_git(["commit", "--no-edit"], cwd=root, check=False, env=dc.git_env())
            if commit.returncode != 0:
                abort_merge(root)
                dc.eprint("join: could not commit the resolved merge: %s" % (commit.stderr or commit.stdout).strip())
                write_join_result(root, joined, branch, conflicts, "commit failed")
                return dc.EXIT_CONFLICT
            joined.append(branch)
            continue

        abort_merge(root)
        dc.eprint("join: %s conflicts with %s in:" % (branch, into))
        for c in conflicts:
            dc.eprint("    " + c)
        write_join_result(root, joined, branch, conflicts)
        return dc.EXIT_CONFLICT

    write_join_result(root, joined, None, [])

    if not args.no_gate:
        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parent / "branch_gate.py"),
            "--base-ref",
            "%s/%s" % (remote, cfg["default_branch"]),
        ]
        if not args.push:
            cmd.append("--no-publish")
        print("\njoin: gating the joined head\n    $ %s" % " ".join(cmd[1:]), flush=True)
        code = subprocess.run(cmd, cwd=root).returncode
        if code != 0:
            dc.eprint("join: the gate on the joined head did not pass (exit %d); nothing pushed" % code)
            return code if code in (dc.EXIT_FAIL, dc.EXIT_USAGE) else dc.EXIT_FAIL

    if args.push:
        pushed = dc.run_git(["push", "--quiet", "--no-verify", remote, into], cwd=root, check=False)
        if pushed.returncode != 0:
            dc.eprint("join: push of %s failed: %s" % (into, pushed.stderr.strip()))
            return dc.EXIT_FAIL
        print("join: pushed %s" % into)

    print("join: joined %s" % ", ".join(joined))
    return dc.EXIT_OK


if __name__ == "__main__":
    dc.main_guard(main)
