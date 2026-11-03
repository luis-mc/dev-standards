# DL18 (CIR10 S2): CI template order

Learnings L1, L2, L6 of CIR10 section 2.1, in the `luismc-delivery` workflow templates.

## What changed
- **L1, step order.** In `verify` of all four tracks (ts, go, rust, dotnet): secret scan, install, format, lint, typecheck/build/vet, boundary check, codegen drift, unit, contract, dependency scan. Before, codegen drift ran before format and lint, and (dotnet) the boundary check ran after the tests.
- **L1, gate order.** Each track's `gate.json` lists `fail_fast_order` and its `steps` run in that order (secret-scan, change-notes, guards, lint, typecheck, unit, e2e). Nothing reads the key at run time; the guard does. Documented in `CONTRACT.md`.
- **L2.** The templates already have one Linux job per family (`verify`, `integration`, `e2e`). The guard now fixes that set: any other job name fails.
- **L6.** The ts `run-times` job is a step of the last job (`e2e`), `continue-on-error`. This is the same hunk as DL16 (taken from `origin/claude/DL16-ci-wait-fix`, byte for byte), so the two branches merge without conflict.

## Guards (`tools/test_delivery_ci.py`)
- `check_job_shape`: only family jobs; a job no other job needs must be a required check, else it is "report-only".
- `check_verify_order`: tiers (secret scan, format, lint/typecheck, boundary, codegen, tests); secret scan first.
- `gate_steps_run_cheapest_first`: `gate.json` order and list.
- Mutants: a report-only job added to ts, go, rust, dotnet fails; a job with another name fails; swapped steps fail in every track.

## Checks run
- `workflows_conform`, `workflow_checker_detects_each_defect`, `gate_steps_run_cheapest_first` (run by name; the session guard refuses the full `delivery-ci` run locally): pass.
- `ts_ci_plan_job_is_in_the_template`, `ts_ci_runs_by_hand_and_reports_times`, `run_times_summary_and_report_only` in `test_ci_speedups.py`: pass.
- `docs_check`: see the last commit.
- Not run: the full `delivery-ci` suite and `spec-lint.yml` (no Actions here). `ci_areas.py --branch-advice` said to run `gh workflow run spec-lint.yml ... -f areas=specs,delivery,artifacts,profiles,transcript-folds,docs`; the owner or CI starts it.

## Not done, on purpose
- No `needs: verify` on `integration`/`e2e-shard`. It would stop the big suites after a red cheap check, but it lengthens a green run by the whole of `verify`, and the exact `if:` guards would need a second form. Not in the contract; for the owner to decide.
- No new required `verify` job that judges the others. The required check names stay as they are.

## Shared files (other steps touch them too)
- `templates/ts/.github/workflows/ci.yml` (S1 merges DL16's identical hunk).
- `tools/test_delivery_ci.py`, `tools/test_ci_speedups.py` (DL16's edits included).
- `templates/shared/scripts/delivery/CONTRACT.md`, `docs/features/delivery-speed/spec.md` (R5.10 added at the end of section 5), `docs/features/delivery/spec.md` (note only; S11 rewrites section 13).
