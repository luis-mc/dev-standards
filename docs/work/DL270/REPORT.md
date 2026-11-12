# DL270 report

Base check: `light_slots` in machine_slots.py and `print_slots` in delivery_ci.py both present on origin/main.

## What changed
- delivery_ci.py `print_slots`: prints `light N  free` or the holder line (repo, run, job, runner, held time, STALE) after the CI slots. Nothing extra when light_slots is 0. `--json` unchanged.
- delivery_doctor.py machine.slots: stale light locks are reported as `slot light-N held by ...`; the ok line reads `no stale slot (N CI, M light), no old ticket`. The doctor never freed slots itself; it points at the next gate or `machine_slots.py free-stale`, which already frees stale light locks.
- New tests: claude/plugins/delivery/tests/test_dl270_light_slot_listing.py.
- Docs: runner-pool spec R5.3 sentence; notes in features/runner-pool/changes, features/delivery/changes (needed to satisfy docs check M1) and docs/architecture/changes/DL270-light-slot-listing.md.

## Tests
- test_dl270_light_slot_listing.py: 5 OK
- test_machine.py (67) and test_dl267_light_slot.py (10): OK
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed
- docs_check.py: only W1 on docs/work/ (expected on a branch)
- spec-lint.yml areas=delivery (run 43286441028): every delivery job success; only the docs check job failed, on W1 for docs/work/ (expected).

## Follow-ups
- A `delivery_ci.py` area test might want a stale-light fix test through free_stale; not in scope.
READY
