# DL389 report

Files:
- claude/plugins/delivery/templates/shared/scripts/delivery/delivery_common.py (Context.full; e2e selection and plan_step use it, not `widened`). branch_gate.py needed no change: it already passes `--full` into the context.
- tools/test_delivery_gate.py (new scenario e2e_widen; two old assertions that expected widening to mean the full suite now expect the selected specs)
- docs/architecture/changes/DL389-e2e-widen-full.md, docs/features/delivery-speed/changes/DL389.md, docs/features/delivery-speed/spec.md (DL4 row)

Tests:
- `python3 tools/test_delivery_gate.py --no-mutants -k e2e`: 77 checks, 0 failed
- `python3 claude/plugins/docs/scripts/docs_check.py`: only error is W1 (this report under docs/work/ on the branch, expected; stripped before the join). No other findings.

Branch head SHA: see `git rev-parse origin/DL389-e2e-widen-full` (a report cannot hold its own commit hash).

READY
