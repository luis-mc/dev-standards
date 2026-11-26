# DS259, DS260, DS264 report

Branch: `DS259-watcher-gate`. Three commits, one per task.

## DS259 test the merge result before merging (DL-119, R5.77)
- `delivery_watch.py`: `merge_result_ok` runs before `gh pr merge`. It reads `behind_by` from the GitHub compare API and builds the merge tree with `git merge-tree --write-tree origin/BASE HEAD`. A head whose own tree equals it merges. `warn` (default) prints one line, records `merge.untested_result`, merges. `update` runs `gh pr update-branch N --expected-head-sha SHA`, records `merge.branch_updated`, waits for CI on the new head.
- `ci_watch.py`: one line after a green run whose open PR head is behind its base.
- Config `watcher.merge_result` in the schema, `delivery_config.py` and the README.
- Tests: `claude/plugins/delivery/tests/test_ds259_merge_result.py` (12).

## DS260 retry an infrastructure failure once (DL-120, R5.78)
- `delivery_watch.py`: `retry_infra` before a train goes red. Classes: startup_failure, runner_lost, before_project_step, log:<pattern>. Any non-infrastructure failed job means no retry. One retry per head (`ci.retried` in the train). Event `ci.retry` names the class.
- Config `watcher.infra_retry` (default false) and `watcher.infra_retry_patterns`.
- Tests: `test_ds260_infra_retry.py` (13).

## DS264 quarantine and one full run (DL-121, DL-122, R5.79, R5.80)
- New `quarantine_check.py` (check, line, names), `.delivery/quarantine.json` described in CONTRACT.md, hook line in `hook_session_start.py`.
- `gate.json` `local_gate` `smoke`: `plan_step` skips an e2e step whose specs cannot be named; `branch_gate.py` prints the one-line note. `--full` and the default are unchanged.
- Tests: `test_ds264_quarantine_smoke.py` (15). Named gate cases `affected` and `config_errors` of delivery-gate pass.

## Checks run
Plugin unit tests above plus test_watch, test_config, test_ds235d_release_optout: 158 OK. `change_notes.py check` ok. `docs_check.py`: no errors. Full delivery-ci and delivery-gate suites left to CI (session guard).

## Notes
- DELIVERYSPEC rows are DL-119 to DL-122 and feature requirements R5.77 to R5.80; the parallel CI-templates agent may use the same numbers, so renumber at the join if both land.
- `tools/test_delivery_gate.py` SCRIPT_FILES and `tools/ci_areas.py` list no similar script, so they are unchanged.

READY
