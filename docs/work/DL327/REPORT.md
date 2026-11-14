# DL327 report: heavy slot class

## Files
- `claude/plugins/delivery/scripts/machine_slots.py`: `heavy_slots`, `runner_gate.heavy_jobs`, `is_heavy_job`, `heavy-N.lock` slots in take/free/find/stale/status; heavy is never light.
- `claude/plugins/delivery/scripts/runner_load_gate.py`: `queue_wait` takes the heavy slot first (no CI slot, no ticket while it waits), then the CI wait; frees the heavy slot if no CI slot comes.
- `claude/plugins/delivery/scripts/runner_job_done.py`: unchanged; `find_held` now finds heavy locks, so one call frees both.
- `claude/plugins/delivery/scripts/delivery_doctor.py`: `machine.heavy` check (warns when heavy_slots > ci_slots); stale heavy slots in `machine.slots`.
- `claude/plugins/delivery/tests/test_dl327_heavy_slots.py`: 10 tests.
- `docs/features/runner-pool/spec.md`: R5.42 to R5.45 and a test row. `docs/features/runner-pool/changes/DL327.md`, `docs/architecture/changes/DL327-heavy-slots.md`.

## Tests (in claude/plugins/delivery/tests)
- `python -m unittest test_dl327_heavy_slots`: 10 tests, OK.
- `python -m unittest test_dl267_light_slot test_dl270_light_slot_listing test_dl105_gate_text test_dl130_gate_fixes test_dl200_gate_vanished_ticket test_machine`: 95 tests, OK.
- `python -m unittest test_dl188_doctor_tools test_dl184_pool_doctor_agree`: 28 tests, OK.
- `docs_check.py`: two errors, both not from code. G1 (generated `decisions.md` stale) was already stale and is not edited by rule. W1 is this work folder, stripped before the join.

## Example machine.json
```json
{
  "ci_slots": 2,
  "heavy_slots": 1,
  "runner_gate": {
    "heavy_jobs": ["integration", "e2e-*", "owner/repo:full"]
  }
}
```

## Branch head
See the last commit on `DL327-heavy-slots` (SHA in the final reply).

READY
