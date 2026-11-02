#!/usr/bin/env python3
"""Refuse a push that changes e2e spec files unless they were run and passed (DELIVERYSPEC DL-88).

    e2e_push_check.py --commit SHA [--base-ref REF] [--branch NAME]

Called by the pre-push hook once per pushed branch. It lists the e2e spec files (gate.json
"e2e_spec_paths") the push adds or changes: the diff from --base-ref (the remote's old head)
to --commit, or, for a new branch (--base-ref auto), from the merge base with the branch it
was cut from. With none, it allows the push. Otherwise .delivery/gate-result.json must be for
exactly --commit and its e2e record must show every changed spec ran and passed (or the whole
suite ran and passed). If not, it names the specs and the command to run, and exits 1: an e2e
fix is never pushed unrun.

Exit: 0 allowed, 1 refused, 2 usage/configuration error.
"""
from __future__ import annotations

import argparse
import sys

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="e2e_push_check.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--commit", required=True)
    ap.add_argument("--base-ref", help="the remote's old head, or 'auto' for a new branch")
    ap.add_argument("--branch", default="")
    args = ap.parse_args(argv)
    root = dc.repo_root()
    cfg = dc.load_gate(root)
    head = dc.rev(args.commit, root)
    if head is None:
        raise dc.DeliveryError("commit '%s' does not resolve" % args.commit)
    base = args.base_ref
    if not base or base == "auto":
        base = dc.fork_point_base(root, head, cfg["default_branch"], args.branch)
    names = dc.run_git(["diff", "--name-only", "--diff-filter=d", base + "..." + head], cwd=root, check=False).stdout.split()
    specs = dc.changed_e2e_specs(names, cfg)
    if not specs:
        return dc.EXIT_OK
    result = None
    try:
        result = dc.read_json(root / dc.GATE_RESULT_PATH)
    except (OSError, ValueError):
        pass
    problems = (
        dc.e2e_problems(result, head, specs)
        if isinstance(result, dict)
        else ["no gate result found (%s)" % dc.GATE_RESULT_PATH]
    )
    if not problems:
        return dc.EXIT_OK
    dc.eprint("e2e-push: blocked. This push changes e2e specs that were not run and passed for this commit:")
    for f in specs:
        dc.eprint("    " + f)
    for p in problems:
        dc.eprint("  - " + p)
    dc.eprint("  Run them (at most 2 workers on a PC), then push again: " + dc.E2E_COMMAND)
    return dc.EXIT_FAIL


if __name__ == "__main__":
    dc.main_guard(main)
