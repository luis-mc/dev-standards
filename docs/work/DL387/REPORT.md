# DL387 report

Fix: e2e_push_check.py now keeps only the pushed spec files that also differ from the merge base of the new head and origin/<default> (new helper `own_changed_files` in delivery_common.py). branch_gate.py already diffs from that same merge base, so no change there; the two agree.

## Files
- claude/plugins/delivery/templates/shared/scripts/delivery/delivery_common.py
- claude/plugins/delivery/templates/shared/scripts/delivery/e2e_push_check.py
- tools/test_delivery_gate.py (scenario e2e_merge, the 5 cases)
- docs/features/delivery/spec.md (R5.14, DL-88 wording; the DL-88 row is there, not in delivery-speed)
- docs/features/delivery/changes/DL387.md, docs/architecture/changes/DL387-e2e-push-merge-base.md

## Tests
- python3 tools/test_delivery_gate.py --no-mutants -k e2e_merge: 10 checks, 0 failed
- ... -k e2e: 71 checks, 0 failed
- ... -k hook: 72 checks, 0 failed

## docs_check
python3 claude/plugins/docs/scripts/docs_check.py: 1 error, W1 (docs/work/ exists on this branch; expected, stripped before the join). Nothing else.

## Code head (before this report commit)
22b55e33f14df42cdf444aad36f35a01da6d8b1c

READY
