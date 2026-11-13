# DL316 report

Done: DL316 (--only), DL317 setup part (CI_RUNS_ON_WINDOWS, label removal), DL319 (symlink right), DL320 (PowerShell host-load task).

## Files

- `claude/plugins/delivery/scripts/delivery_runner_pool.py`: `plan(only=)`, `--only` in its CLI, `generic_label_set`, `windows_runs_on`, `workflows_naming`, `host_load_task_ps`, `remove-label` step and handler, `SeCreateSymbolicLinkPrivilege` in `RIGHTS_PS`, `CI_RUNNER_RIGHTS` marker in the runner `.env`.
- `claude/plugins/delivery/scripts/delivery_ci_setup.py`: `--only windows|linux`, prints plan notes.
- `claude/plugins/delivery/commands/delivery-ci-setup.md`: `--only windows`, `CI_RUNS_ON_WINDOWS`.
- `claude/plugins/delivery/tests/test_dl316_windows_only_generic.py` (new, 15 tests).
- Existing tests updated for new behaviour: `test_dl310_windows_runner.py` (env marker line), `test_runner_pool.py` (host-load task is PowerShell, not schtasks). Both are outside `owns`; the change is two assertions.
- `docs/features/runner-pool/spec.md` (R5.31, R5.32 text; new R5.35, R5.36, R5.37; test row), `docs/features/runner-pool/changes/DL316.md`, `docs/architecture/changes/DL316-windows-only-generic.md`.

## Tests

- `python -m unittest test_dl316_windows_only_generic test_dl310_windows_runner test_dl315_runner_remove_token test_runner_pool test_ci_setup` (in `claude/plugins/delivery/tests`): 240 tests, OK.
- `docs_check.py`: G1 (decisions.md stale, generated, not touched), W1 (docs/work, expected on a branch). M1 answered by a `Docs: none` line in the commit message.

## Needs outside `owns`

- `machine_slots.py`: `generic_labels` is read raw from machine.json (`read_config_file`). `normalise_config` and `CONFIG_KEYS` do not know the key, so `write_machine_config` (the `machine-config` step) drops it on rewrite. Add `generic_labels` (list of strings) to `DEFAULT_CONFIG` and `normalise_config`.
- Doctor: no check yet that a Windows runner has the symlink right or no project label.

## Notes

- A kept runner whose `.env` lacks `CI_RUNNER_RIGHTS=symlink-1` is treated as stale: the account step runs again (adds the right) and the service restarts. No new password.
- Label removal `names` entry the owner must give with `--yes-delete`: `label <label> on runner <runner> in <owner/repo>`.
- Branch head before this report commit: c75b6d207a4c2afd391195ad8bd254c71da5920e.

READY
