# DL16: CI wait fix (dev-standards side)

Status: step 3 done here; steps 1 and 2 do not apply to the generic template (see below). The comics-organizer branch carries steps 1 to 3 for its own workflow.

## What changed in the ts template
- `run-times` is no longer a job. Its three steps (checkout, `ci_run_times.py`, upload of `ci-run-times`) are the last steps of the `e2e` job, gated by `CI_RUN_TIMES == 'true'`, `continue-on-error: true`, `if: always()`. `e2e` now also needs `verify` and `integration`, so it is the last job.
- Tests: `tools/test_ci_speedups.py` (run-times is a step of the last job, never fails), `tools/test_delivery_ci.py` (required `e2e` needs list and its mutant).

## Why steps 1 and 2 are not here
- The generic template has no "Linux suites (one job)" and no report-only jobs: `verify`, `integration` and `e2e-shard` run real work. There is nothing to skip by an `if:` on the plan.
- Its secret scan is already a step in `verify` (no job of its own).
- `runner_plan.py` in this repo is the local heavy-job wrapper, not a CI planner. The planning step of comics-organizer is `scripts/ci/plan.ts` and `scripts/runners-check.ts`, which are project code.

## Checks run
- `python3 tools/test_ci_speedups.py`: 24 passed.
- `python3 tools/test_delivery_ci.py`: 77 passed.
- `python3 tools/test_delivery_runner.py`: all passed.
- Not run: `spec-lint.yml` on the branch (no Actions from this sandbox).

## Could not verify
- Whether the new last-step run-times shows the `e2e` job itself as in progress in the report (it did show the run-times job itself in progress before; expected, report only).
