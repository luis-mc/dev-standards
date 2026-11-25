# DS246 report: remove the load, slot and runner layer

Branch: `DS246-remove-load-slot-layer`. Not merged, no PR.

## Removed

- Delivery plugin scripts: `load.py`, `load_guard.py`, `machine_slots.py`, `runner_load_gate.*`, `runner_job_done.*`, and the template `runner_plan.py`.
- The load guard in SessionStart and PreToolUse, and the doctor's runner and load checks.
- The load-gate by-hand item in `delivery_ci_setup.py`.
- Config keys: `manage_runners`, `heavy_jobs_yield`, `heavy_commands`, `runner_plan` retry and report keys. Old configs stay valid (unknown keys warn).
- Tests of the removed code, `tools/test_delivery_runner.py`, and the lock cases in `tools/test_delivery_shared_fixes.py`.
- DELIVERYSPEC rules DL-77, DL-78, DL-79, DL-90, DL-91 (not renumbered; a "Removed rules" section lists them).
- Feature spec requirements R5.9, R5.10, R6.5 and four edge-case rows. `shared-self-hosted-runners.md` now keeps only the CI runs section, the CI runs file and the setup pattern.
- Citations of the removed IDs in code, tests, schema and overview docs.

## Added

- `docs_check.py` rule `R1`: an error when a project with `.delivery/` cites a removed ID. It names the ID and says "removed, delete the citation". Test: `claude/plugins/docs/tests/test_ds246_removed_ids.py`.
- Guide `docs/guides/removed-delivery-ids.md`.
- Change notes for delivery (also names its `plugin.json`), docs, project-setup, delivery-speed and test-cost.
- `tools/ci_areas.py`: the delivery test regex now accepts `_` in the name, so `test_delivery_shared_fixes.py` maps to the delivery area.

## Kept on purpose

- `ci.load_limits` (DL22, per runner, written by CI setup).
- `cloud_ci_sessions` / `cloud_ci_limit` and the ci-wait marker in `ci_fallback.py` and `fallback_launch.py`. Only their rule citations were removed.
- The slot-log reader in `ci_runs.py`.
- DL-50 (heavy local job, `runner_plan`) is not in the removed list. It still mentions `runner_plan`, which now holds only `cancel_replaced_runs` and `hold_dependabot_during_train`. Review it in a later task.

## Tests

- `docs_check.py`: 0 errors, 7 old warnings.
- `claude/plugins/docs/tests`: `test_check`, `test_ds246_removed_ids` pass.
- `tools/test_delivery_hooks.py` 57 pass; `test_delivery_shared_fixes`, `test_delivery_fallback`, `test_delivery_fallback_launch`, `test_ci_areas` pass.
- Plugin delivery tests (1346 run): after fixes to `test_config` and `test_dl318`, the remaining failures are Windows-environment ones in tests this task did not touch: `test_ds235d_os_steps` (bash path), `test_lc*` (lifecycle), gitleaks and scanner tests, `test_e2e_chromium` (path form), `test_dl385_installer_names` (cp1252 read).
- No mutation passes, no Docker.
