# DL351 report: gate hang on the ci-wait marker

## Files
- `claude/plugins/delivery/templates/shared/scripts/delivery/ci_fallback.py`: `_git` non-interactive env, `-c credential.interactive=never`, timeout (`DELIVERY_MARKER_GIT_TIMEOUT`, default 20 s); timeout or missing git is a failed result; `mark_wait` and `claim_taken` return False when git fails.
- `claude/plugins/delivery/scripts/runner_load_gate.py`: `slot N taken` logged before the claim check; each marker step logs one line on failure or timeout and goes on.
- `claude/plugins/delivery/scripts/delivery_doctor.py`: `marker_credential_item` (`machine.markercred:<dir>`), `git ls-remote` with the same env and timeout; locked folder says it needs an administrator shell.
- `claude/plugins/delivery/tests/test_dl351_gate_git_hang.py`
- `docs/features/runner-pool/spec.md` (R5.58, failure-mode line, test row), `docs/features/runner-pool/changes/DL351.md`, `docs/architecture/changes/DL351-gate-git-hang.md`
- `delivery_runner_pool.py` not changed: the pool doctor already runs `machine_items` from `delivery_doctor.py`.

## Tests (all OK)
- `python3 -m unittest claude/plugins/delivery/tests/test_dl351_gate_git_hang.py`: 12 tests
- in `claude/plugins/delivery/tests`: `test_dl292_ticket_heartbeat` 10, `test_dl200_gate_vanished_ticket` 2, `test_doctor` 19, `test_dl267_light_slot` 10, `test_dl327_heavy_slots` 10, `test_load` 48
- `python3 -m unittest test_delivery_fallback` in `tools/`: 28 tests
- `tools/test_delivery_runner.py`: 0 tests collected by unittest
- `docs_check.py`: only W1 (this report under docs/work, branch only, expected).
- No Docker, no mutation passes. `ci_areas.py --branch-advice` says heavy (delivery); not run, per brief.

## Note
The gate's old line `slot N taken after S s; starting the job` is now two lines: `slot N taken after S s`, then `starting the job`.

READY
