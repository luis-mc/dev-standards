#!/usr/bin/env python3
"""The seconds-long checks of the branch gate, for the pre-push hook (STACKSPEC 13.5).

    fast_guards.py [--base-ref REF] [--timeout-minutes N]

Runs the gate.json steps marked "pre_push": true (the guard tests and the secret
scan), continuing past a failure so one run reports everything. Each step has a
time limit (5 minutes); one over it is killed with everything it started and
fails. A failed step is reported the way the branch gate reports one: the
"FAIL <step>: <reason> (exit N, Ns) - log: <path>" line and the last 40 lines of
its output, so a blocked push says which check failed and why. Step logs are in
.delivery/logs/pre-push/. Never writes or publishes a gate result; the pre-push
hook calls it once per pushed ref.

Exit: 0 all passed, 1 a step failed or timed out, 2 usage/configuration error.
"""
from __future__ import annotations

import argparse
import sys

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fast_guards.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-ref", help="ref or commit the pushed work is compared with (default origin/<default_branch>)")
    ap.add_argument("--timeout-minutes", type=float, default=dc.FAST_STEP_TIMEOUT_MINUTES, metavar="N",
                    help="limit for each step (default %d)" % dc.FAST_STEP_TIMEOUT_MINUTES)
    args = ap.parse_args(argv)
    if not args.timeout_minutes > 0:
        ap.error("--timeout-minutes must be greater than 0")

    root = dc.repo_root()
    cfg = dc.load_gate(root)
    steps = [s for s in cfg["steps"] if s["pre_push"]]
    if not steps:
        raise dc.DeliveryError("gate.json has no step with \"pre_push\": true")

    ctx = dc.build_context(root, cfg, args.base_ref)
    print("fast_guards: head %s, base %s, limit %g min per step" % (ctx.head[:10], ctx.base[:10], args.timeout_minutes))
    entries, _ = dc.execute_steps(
        steps,
        ctx,
        keep_going=True,
        limit_seconds=args.timeout_minutes * 60,
        per_step=True,
        log_dir=dc.FAST_LOG_DIR,
    )
    print("\n" + dc.summary_table(entries))
    dc.print_failures(entries, root)
    if dc.overall_pass(entries):
        return dc.EXIT_OK
    if not any(e["outcome"] != "skip" for e in entries):
        dc.eprint("error: no pre_push step ran, so the guards cannot decide")
    return dc.EXIT_FAIL


if __name__ == "__main__":
    dc.main_guard(main)
