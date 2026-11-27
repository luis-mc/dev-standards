# DS287-d report: rerun wiring (R5.92) and unmapped check (R5.94)

Branch `DS287-d-rerun-wiring`, from `origin/DS287-integration`.

## Files
- New `templates/shared/scripts/delivery/rerun_step.py`: `lookup` (previous head, job conclusion, report download, changed files; reuses `carry_plan.py` helpers, which are unchanged), `mode`, `exec`.
- New `templates/shared/.github/actions/rerun-narrow/action.yml`: runs `rerun_tests.py --runner .. --prev-conclusion .. --report .. --changed-file - --json`; any error gives `mode=current`.
- `templates/{ts,go,rust}/.github/workflows/ci.yml`: rerun step, narrow step, normal step (runs unless `mode == narrow`), report upload (`test-report-verify`, `test-report-integration`) in every test job; unmapped check in the plan job (ts `plan`, go and rust `carry`); go and rust `carry-ok` fails when the plan job failed.
- `templates/ci-snippets/ci-areas-pattern.yml`: `changed_areas.py unmapped --check` step.
- `changed_areas.py unmapped --check`, `area_select.py --unmapped [--check]`.
- `scripts/delivery_doctor.py`: new `unmapped` check (warn above 0, names up to 10 files).
- Spec text in `docs/features/delivery/spec.md` (R5.92, R5.94), change note `docs/architecture/changes/DS287-d-rerun-wiring.md`.
- New test `tests/test_ds287_rerun_wiring.py` (21 tests).

## Tests run (python files directly)
All OK: test_ds287_rerun_wiring (21), test_ds287_carry_forward (32), test_ds287_verify_wiring (13), test_ds287_rerun_affected (13), test_ds261_ci_areas (20), test_dl375_rerun_narrowing (33), test_doctor (12), test_ds202_rust_doctor (14). `docs_check.py`: 0 errors.

## Contract points not met or limited
- Only the main test step of each job is narrowed: ts and go `verify` narrow the unit step, not the contract step; the `integration` jobs narrow the integration step, not the authz or route-coverage step.
- The dotnet template is not wired (not in the task).
- Rust narrows with plain `cargo test --locked`, not `rust_ci.py test --lib` (crate scoping env is not applied in narrow mode). Rust reports are the cargo log (`test-report-*.log`), read through `--log`; there is no JSON report. vitest and go reports are JSON.
- Rust has no `then` (no affected-package rule); go `then` needs `go` on PATH in the job, set up before the step.
- The lookup skips runs where the job was skipped (carried) and uses the newest earlier head with a non-skipped job.
- The workflow YAML was checked by parsing and by tests, not run on GitHub. Not run in CI: the artifact download and `gh` lookup.
- The go and rust unmapped check runs only when `scripts/delivery/ci-areas.json` exists (ts too).
