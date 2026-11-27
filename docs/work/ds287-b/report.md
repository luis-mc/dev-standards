# DS287-b report: verify and wiring

## Files
- New `templates/shared/scripts/delivery/carry_verify.py` (R5.91). Adds `--ignore a,b` (not in the brief) so plumbing jobs (`decide`, `plan`, `carry`) and jobs skipped by area or runner kind stay out of the check.
- New `templates/shared/.github/actions/carry-plan/action.yml`. Inputs `workflow`, `map`, `github-token`. Outputs `run`, `carried`, `reason`, `plan`. A missing or failing `carry_plan.py`, or a non-`pull_request` event, gives an empty plan (every job runs) and a warning.
- Wired: `ts|go|rust|dotnet/ci.yml`, `ts|go|rust|dotnet/package.yml`, `shared/package-windows.yml`, `shared/windows-msi-check.yml`, `ci-snippets/ci-areas-pattern.yml`.
  - ts `ci.yml`: the carry step is in the existing `plan` job. `verify` now needs `plan`. The required `e2e` job calls `carry_verify.py` on pull requests (old shard check kept for other events).
  - Others: new `carry` job (own `CRSP_CARRY` runner var) and new `carry-ok` aggregate job (`CRSP_CARRY_OK`).
  - Gate: `needs.carry.result != 'cancelled' && fromJSON(...carry_plan || '{}').run_<job> != 'false'`, ANDed with the existing `if`.
- New `tests/test_ds287_verify_wiring.py` (13 tests). Edited `tests/test_dl181_ci_rerun_first.py` (`verify` needs `[decide, plan]`).

## Tests run (python files directly)
test_ds287_verify_wiring, test_dl147_workflow_needs, test_dl394_runs_on_vars, test_dl181_ci_rerun_first, test_dl191_msi_wine_installed, test_ds261_ci_areas, test_dl245_multi_track, test_ci_setup, test_dl375_rerun_narrowing: all OK. Not run: `carry_plan.py` (other agent's), docs_check.

## Not met / open
- R5.92 template part: not done. No shipped workflow template calls `rerun_tests.py` or passes `--prev-conclusion` (only `ci_rerun_first.py` is called, `workflow_dispatch`/`pull_request`). There is no call to extend. Needs the wiring of `rerun_tests.py` into the test jobs, a separate decision.
- `carry-ok` is a new check name in go/dotnet/rust ci and the package/msi workflows. Branch protection must list it where it should be required (ts keeps `e2e`).
- No docs change note added (`docs_fold.py` not available here); plugin `plugin.json` untouched.
- `carry_plan.py` output format assumed single-line `key=value` lines.
