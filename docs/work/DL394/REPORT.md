# DL394 report: runs-on reads RUNS_ON_* first

## Done
- 15 workflow templates (ts, go, rust, dotnet, shared, runner-pool/pool-check.yml): `runs-on` is now `RUNS_ON_LINUX || CI_RUNS_ON || ubuntu-latest`. The ts nightly reads `NIGHTLY_RUNS_ON || RUNS_ON_LINUX || CI_RUNS_ON`. The rust/ts pool-twin `contains(...)` conditions read the same pair. `package-windows.yml` build job reads `RUNS_ON_WINDOWS || CI_RUNS_ON_WINDOWS || windows-latest`. No template declares a Windows size, so `RUNS_ON_WINDOWS_<SIZE>` is documented only.
- `delivery_ci_setup.py`: plan step is `var:RUNS_ON_LINUX` (was `var:CI_RUNS_ON`). The check accepts an existing correct `CI_RUNS_ON`.
- `delivery_doctor.py`: `resolve_runs_on`, `runs_on_items` (item `workflows.runs_on:<repo>` says which variable each OS resolves to; `workflows.runs_on_both:<repo>` warns when both differ). `machine.runs_on` accepts any of the variables.
- `delivery_ci_install.py`: generated job uses the new expression.
- Docs: CONTRACT.md U5/U6, delivery-ci-setup.md, DELIVERYSPEC DL-90 text, feature spec R5.63 (new), R5.53, R13.13. Notes: docs/architecture/changes/DL394-runs-on-vars.md, and features delivery, delivery-speed, runner-pool.
- Tests: new `tests/test_dl394_runs_on_vars.py`; expectations updated in test_ci_setup, test_dl184, test_dl187, test_dl190, `tools/test_delivery_ci.py`, `tools/test_ci_speedups.py`, `tools/test_smoke_packaged.py`.

## Not changed (outside the ownership list)
- `delivery_runner_pool.py` still writes `CI_RUNS_ON` / `CI_RUNS_ON_WINDOWS` (plan ids `var:CI_RUNS_ON:<repo>`). That still works (old variable is the fallback).
- `templates/shared/scripts/delivery/runner_health.py` only reads `vars.CI_RUNS_ON`; it should learn `RUNS_ON_LINUX` in a follow-up.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl394_runs_on_vars test_dl184_pool_doctor_agree test_ci_setup test_dl318_doctor_locked_runner test_dl316_windows_only_generic test_dl187_ci_templates_pool test_dl190_pool_integration_job test_dl341_pool_all_oses test_machine test_runner_pool`: 329 OK.
- `tools/test_delivery_ci.py` (template/pool/runs-on/mutant cases only, 20 cases): 0 failed. The full suite is declared heavy and was not re-run.
- `tools/test_ci_speedups.py`: 24 passed.
- `tools/test_smoke_packaged.py`: 2 failed (workers stop checks). Same 2 fail on origin/main without my changes.

## docs_check
`python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 1 warning (tools/test_ci_speedups.py unmapped, existed before).

## Head
See `git rev-parse HEAD` on branch DL394-runs-on-vars (the last commit).

READY
