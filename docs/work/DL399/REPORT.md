# DL399 report: per-job runner variable CRSP_<JOB>

Status: checks done, committing.

## Files
- 37 `runs-on` lines in 15 templates (`claude/plugins/delivery/templates/**`, incl. `lifecycle-lanes.yml`, `pool-check.yml`): `vars.CRSP_<JOB>` first, chain unchanged. `ci-fallback.yml` has a literal hosted label, left alone.
- `scripts/delivery_doctor.py`: `job_var_name`, `per_job_overrides`; the runner report lists set overrides.
- `tests/test_dl394_runs_on_vars.py`: order test now needs CRSP_<job key> first; name rule test; lifecycle test; doctor test.
- `CONTRACT.md` (U5/U6), `commands/delivery-ci-setup.md`: rule and way back.
- `docs/features/delivery/spec.md` R5.64; change notes in `docs/architecture/changes/` and `docs/features/*/changes/`.

## Tests
- `python3 -m unittest test_dl394_runs_on_vars test_dl318_doctor_locked_runner test_ci_setup` (in tests/): 48 OK.
- All delivery tests that mention workflows or runs-on variables: 754 OK, 1 skipped.
- `ci_areas.py --branch-advice`: "unreadable diff"; no workflow was started.

## docs_check
See last run in the commit step: no errors after the notes.
