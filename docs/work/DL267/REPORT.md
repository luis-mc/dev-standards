# DL267 report

Base check: OK. Both scripts exist; machine_slots.py had `'ci_slots': 2`.

## What changed
- `machine_slots.py`: `light_slots` (default 1, min 0), `runner_gate.light_jobs` (default list, fnmatch), `slots/light-N.lock`, `is_light_job`, `take_slot(kind='light')`, `free_slot`/`find_held`/`free_stale` handle light locks, `status()` has `light_slots`, log lines carry `slot_kind`.
- `runner_load_gate.py`: a light job takes a light slot at once (no ticket, load limits apply), falls back to a CI slot in queue order when all light slots are busy. Log: `slot light-1 taken after N s`.
- `runner_job_done.py`: log line uses the slot label only (find_held finds light locks).
- Docs: runner-pool spec R5.1/R5.2/R5.3 (the machine.json and slot paragraphs now live there), plugin README, design doc machine.json block, feature note, change note.
- Tests: new `test_dl267_light_slot.py` (10 tests); `test_machine.py` line 90 pin updated for the new `light_jobs` default.

## Tests
- `python3 -m unittest test_dl267_light_slot` in tests/: 10 OK.
- test_machine, test_dl200, test_dl118, test_load, test_runner_pool, test_doctor: 295 OK after the pin fix.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- docs_check: only W1 (expected) and M1 on the plugin README (already there before).

## Follow-ups
- `delivery_ci.py slots` listing and the doctor stale-slot check read only CI slots; JSON status has `light_slots`. Not owned here.
- Files outside the owns list edited for docs: runner-pool spec, README, shared-self-hosted-runners.md.

CI: spec-lint run 43129276102 (areas=delivery): every delivery job passed; only `docs check` failed, on the expected W1 (docs/work/ on a branch).

Branch head SHA: a39eb24 (code; the report commit follows)

READY
