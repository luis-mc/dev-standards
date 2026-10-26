# DS84 report: runner gate and the Windows PowerShell execution policy

Done: README "Windows runner (service)" bullet (invocation, execution policy for the service account, Python access,
exact-as-runner test, watch the first job); doctor `runner` check reads the service account's effective execution
policy on Windows for a `.ps1` hook (registry and service reads isolated in `_service_account`, `_account_sid`,
`_effective_policy`); tests with those mocked; change note (minor).

The "(or .cmd; check your runner version ...)" hedge was left: no runner source or docs were available to confirm it.

Files changed: claude/plugins/delivery/README.md, scripts/delivery_doctor.py, tests/test_doctor.py,
docs/specs/changes/DS84-runner-gate-execution-policy.md, this report.

Tests: `python -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests` (how CI runs it):
8 new tests pass. 4 failures exist with and without this change (missing tzdata on this PC: test_all_ok,
test_cli_exit_codes_and_output, test_train_id_uses_owner_timezone_day, test_sample_project_config_and_template_are_valid).

Open: not run against a real service account here; the first real job should be watched.
