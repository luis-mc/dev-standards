#!/usr/bin/env python3
"""Decide whether a branch's published gate result can be trusted (STACKSPEC 13.5).

    gate_verify.py BRANCH [--base-ref REF] [--remote origin] [--allow-older-base] [--strict-base] [--json]

Fetches the branch, the base ref and refs/gate-results/BRANCH, then applies the
trust rule from CONTRACT.md: the result's head is the branch's current head on
the remote, its base is the current head of the branch it joins, and it passed.
--allow-older-base relaxes the base condition to "base is an ancestor of the
current head of the branch it joins" (join.py does not gate the joined head; the ready PR's CI does).
A result whose base is an ancestor of the current base stays valid when every
commit in between touches only inert paths (gate.json "inert_paths", default
docs/**): the ready pull request's CI still tests the real merge. --strict-base
turns that off, so any move of the base makes the result stale.

A result is also refused when a required step (gate.json "required_steps", default typecheck and
lint) is missing or was skipped for any reason other than "nothing in its scope changed".

Exit: 0 trusted and passing, 1 not trusted, 2 no result (or branch not found).
"""
from __future__ import annotations

import argparse
import json
import re
import sys

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc

_SHA = re.compile(r"^[0-9a-f]{40}$")


def _fetch(remote: str, src: str, dst: str, root) -> bool:
    p = dc.run_git(["fetch", "--quiet", remote, "+%s:%s" % (src, dst)], cwd=root, check=False)
    return p.returncode == 0


def verify(
    branch: str,
    base_ref: str,
    remote: str = "origin",
    allow_older_base: bool = False,
    root=None,
    strict_base: bool = False,
) -> dict:
    """The verdict as a dict: trusted, exit, reasons, plus the shas involved."""
    root = root or dc.repo_root()
    verdict: dict = {
        "branch": branch,
        "base_ref": base_ref,
        "remote": remote,
        "trusted": False,
        "exit": dc.EXIT_FAIL,
        "reasons": [],
        "branch_head": None,
        "base_head": None,
        "result_head": None,
        "result_base": None,
        "inert_commits": None,
    }

    def refuse(code: int, reason: str) -> dict:
        verdict["exit"] = code
        verdict["reasons"].append(reason)
        return verdict

    tracking = "refs/remotes/%s/%s" % (remote, branch)
    if not _fetch(remote, "refs/heads/" + branch, tracking, root):
        return refuse(dc.EXIT_USAGE, "branch '%s' not found on remote '%s'" % (branch, remote))
    verdict["branch_head"] = dc.rev(tracking, root)

    if base_ref.startswith(remote + "/"):
        name = base_ref[len(remote) + 1 :]
        if not _fetch(remote, "refs/heads/" + name, "refs/remotes/%s/%s" % (remote, name), root):
            return refuse(dc.EXIT_USAGE, "base branch '%s' not found on remote '%s'" % (name, remote))
    base_head = dc.rev(base_ref, root)
    if base_head is None:
        return refuse(dc.EXIT_USAGE, "base ref '%s' does not resolve" % base_ref)
    verdict["base_head"] = base_head

    fetched = dc.FETCHED_REF_PREFIX + "%s/%s" % (remote, branch)
    if not _fetch(remote, dc.RESULT_REF_PREFIX + branch, fetched, root):
        return refuse(
            dc.EXIT_USAGE,
            "no gate result published for '%s' (run scripts/delivery/branch_gate.py on the branch)" % branch,
        )
    shown = dc.run_git(["show", "%s:%s" % (fetched, dc.RESULT_FILE_IN_REF)], cwd=root, check=False)
    if shown.returncode != 0:
        return refuse(dc.EXIT_FAIL, "the result ref holds no %s" % dc.RESULT_FILE_IN_REF)
    try:
        result = json.loads(shown.stdout)
        if not isinstance(result, dict):
            raise ValueError("not an object")
    except ValueError as exc:
        return refuse(dc.EXIT_FAIL, "the result is not valid JSON (%s)" % exc)

    reasons: list[str] = verdict["reasons"]
    verdict["result_head"] = result.get("head")
    verdict["result_base"] = result.get("base")

    if result.get("schema") != dc.SCHEMA or result.get("kind") != "branch-gate":
        reasons.append("not a branch-gate result of schema %d" % dc.SCHEMA)
    if result.get("branch") != branch:
        reasons.append("result is for branch '%s', not '%s'" % (result.get("branch"), branch))

    r_head, r_base = result.get("head"), result.get("base")
    if not (isinstance(r_head, str) and _SHA.match(r_head)) or not (
        isinstance(r_base, str) and _SHA.match(r_base)
    ):
        reasons.append("result head/base are not 40-hex commit ids")
    else:
        if r_head != verdict["branch_head"]:
            reasons.append(
                "stale head: result is for %s, the branch is now at %s"
                % (r_head[:10], (verdict["branch_head"] or "?")[:10])
            )
        if r_base != base_head:
            if allow_older_base and dc.is_ancestor(r_base, base_head, root):
                pass  # an older base is acceptable: the joined head is covered by the ready PR's CI
            elif allow_older_base:
                reasons.append(
                    "base %s is not an ancestor of %s (%s)" % (r_base[:10], base_ref, base_head[:10])
                )
            else:
                inert_ok, n_inert = False, 0
                if not strict_base:
                    try:
                        inert = dc.load_gate(root)["inert_paths"]
                    except dc.DeliveryError:
                        inert = []
                    inert_ok, n_inert, _bad = dc.inert_only(r_base, base_head, inert, root)
                if inert_ok:
                    verdict["inert_commits"] = n_inert  # the base moved, but only by inert commits
                else:
                    reasons.append(
                        "stale base: result was gated against %s, %s is now at %s"
                        % (r_base[:10], base_ref, base_head[:10])
                    )

    if result.get("partial"):
        reasons.append("partial result (--only/--skip/--no-setup was used)")
    if result.get("timed_out"):
        reasons.append("the gate timed out")
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    if any(isinstance(s, dict) and s.get("name") == dc.SETUP_STEP and s.get("outcome") != "pass" for s in steps):
        reasons.append("setup did not pass (a stale lockfile is the usual cause)")
    required = result.get("required_steps")
    if not isinstance(required, list):  # a result written before required_steps: lint and types, where it has them
        required = [n for n in dc.DEFAULT_REQUIRED_STEPS]
        have = {s.get("name") for s in steps if isinstance(s, dict)}
        required = [n for n in required if n in have]
    by_name = {s.get("name"): s for s in steps if isinstance(s, dict)}
    for name in required:
        entry = by_name.get(name)
        if entry is None:
            reasons.append("required step '%s' is not in the result" % name)
        elif entry.get("outcome") == "skip" and not str(entry.get("reason") or "").startswith("no "):
            # "no package changed" / "no ui_paths change" mean nothing to check; any other skip means it never ran
            reasons.append("required step '%s' did not run (%s)" % (name, entry.get("reason") or "skipped"))
    if result.get("pass") is not True:
        failed = [s.get("name") for s in steps if isinstance(s, dict) and s.get("outcome") == "fail"]
        reasons.append("result is failing" + (" (failed: %s)" % ", ".join(failed) if failed else ""))

    verdict["trusted"] = not reasons
    verdict["exit"] = dc.EXIT_OK if verdict["trusted"] else dc.EXIT_FAIL
    return verdict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gate_verify.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("branch")
    ap.add_argument("--base-ref", help="branch it joins (default <remote>/<default_branch>)")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--allow-older-base", action="store_true")
    ap.add_argument("--strict-base", action="store_true",
                    help="any move of the base makes the result stale (no inert_paths exception)")
    ap.add_argument("--json", action="store_true", help="print the verdict as JSON")
    args = ap.parse_args(argv)

    root = dc.repo_root()
    base_ref = args.base_ref
    if not base_ref:
        base_ref = "%s/%s" % (args.remote, dc.load_gate(root)["default_branch"])

    v = verify(args.branch, base_ref, args.remote, args.allow_older_base, root, args.strict_base)
    if args.json:
        print(json.dumps(v, indent=2))
    elif v["trusted"]:
        print(
            "TRUSTED: %s head %s, gated against %s %s%s"
            % (
                args.branch,
                v["result_head"][:10],
                base_ref,
                v["result_base"][:10],
                " (older base allowed)" if v["result_base"] != v["base_head"] and v["inert_commits"] is None else "",
            )
        )
        if v["inert_commits"] is not None:
            print("  base moved only by inert commits: %d" % v["inert_commits"])
    else:
        print("NOT TRUSTED: %s" % args.branch)
        for reason in v["reasons"]:
            print("  - " + reason)
    return v["exit"]


if __name__ == "__main__":
    dc.main_guard(main)
