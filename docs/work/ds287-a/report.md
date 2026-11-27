# DS287-a report: carry plan

Branch `DS287-a-carry-plan`, from `origin/DS287-integration`. Contract: R5.88, R5.89, R5.90, R5.93.
All files are in `claude/plugins/delivery/`.

## Files

- `templates/shared/scripts/delivery/carry_plan.py` (new): planner and CLI (R5.88, R5.89).
- `templates/shared/scripts/delivery/carry_replay.py` (new): read-only replay (R5.93).
- `templates/shared/scripts/delivery/area_select.py`: `lock_jobs`, `script_jobs`, workflow-file rule, `parse_workflow_jobs`, `--workflow`, `--workflow-path` (R5.90).
- `templates/shared/scripts/delivery/ci_scope.py`, `changed_areas.py`: `--carry` (R5.89).
- `tests/test_ds287_carry_forward.py` (new): 32 tests.

## Tests run (python files directly)

- `test_ds287_carry_forward.py`: 32 tests, OK.
- `test_ds261_ci_areas.py`: 20 tests, OK.
- `test_dl121_port_fixes.py`, `test_dl181_ci_rerun_first.py`, `test_dl245_multi_track.py`, `test_dl294_rust_release_scope.py`: OK (they use the three edited scripts).
- No Docker, no mutation passes, no full suites.

## Choices to know

- A job the map does not list (for example `plan`) is never carried: it runs.
- A matrix job with a failed or skipped leg is not a proof.
- No changed path since the proof head carries every proven job (an empty diff is not "run everything" here).
- `script_jobs` needs the workflow text. Without it, or without a `ci_tests` area and a naming job, the script falls to `run_everything`.
- The workflow-file rule is active only when `workflow_path` is given, so old behaviour is unchanged.
- `carry_plan.py` takes an extra `--base-ref`. It defaults to the pull request's base from the API. It needs `origin/<base>` in the checkout.
- `carry_replay.py` without `--workflow` replays every active workflow that has runs on the pull request.

## Not met / not done

- No test lists the shipped scripts (grep found none), so nothing was added there.
- `carry_plan.py` and `carry_replay.py` live-API paths (`gh`, `git fetch pull/N/head`) are not run in tests (no network). The pure planner, git part and replay core are tested.
- No change note and no `docs_check.py` run: the task said `Docs: none`. AGENTS.md asks for a change note naming the plugin's `plugin.json` when plugin files change; the release fold or the integration branch owner should add it.
- The workflow `ci.yml` templates do not call `carry_plan.py` yet (outside this task).
