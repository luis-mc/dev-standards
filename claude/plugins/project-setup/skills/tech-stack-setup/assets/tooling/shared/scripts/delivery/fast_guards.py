#!/usr/bin/env python3
"""The seconds-long checks of the branch gate, for the pre-push hook (STACKSPEC 13.5).

    fast_guards.py [--base-ref REF]

Runs the gate.json steps marked "pre_push": true (the guard tests and the secret
scan), continuing past a failure so one run reports everything. Never writes or
publishes a gate result; the pre-push hook calls it once per pushed ref.

Exit: 0 all passed, 1 a step failed, 2 usage/configuration error.
"""
from __future__ import annotations

import argparse

import delivery_common as dc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fast_guards.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-ref", help="ref or commit the pushed work is compared with (default origin/<default_branch>)")
    args = ap.parse_args(argv)

    root = dc.repo_root()
    cfg = dc.load_gate(root)
    steps = [s for s in cfg["steps"] if s["pre_push"]]
    if not steps:
        raise dc.DeliveryError("gate.json has no step with \"pre_push\": true")

    ctx = dc.build_context(root, cfg, args.base_ref)
    print("fast_guards: head %s, base %s" % (ctx.head[:10], ctx.base[:10]))
    entries = dc.execute_steps(steps, ctx)
    print("\n" + dc.summary_table(entries))
    if dc.overall_pass(entries):
        return dc.EXIT_OK
    if not any(e["outcome"] != "skip" for e in entries):
        dc.eprint("error: no pre_push step ran, so the guards cannot decide")
    return dc.EXIT_FAIL


if __name__ == "__main__":
    dc.main_guard(main)
