# DL249 report

Base check: join.py printed `conflicts with` and handled Cargo.lock on origin/main. OK.

## What changed
- `join.py`: conflict lines always list files (`(files unknown)` if none); printed once, in `finish_partial`.
- `join.py`: a conflict only in generated docs takes integration's version, runs `docs_index.py build`, commits, continues, prints one line. Other files too: normal conflict. The list is fixed in join.py (no generated list exported by the docs plugin).
- `delivery_watch.py`: a held run is recorded with `state: held`, prints a `HELD run ... not a failure` line, and a line when re-run.
- Spec R5.58, feature note DL249, change note DL249-join-conflicts-held-runs.

## Part 3 cause (startup_failure)
Not found in this repo. Checked: `delivery_watch.py` (it only cancels and re-runs; it never touches CI_RUNS_ON), `templates/shared/scripts/delivery/runner_plan.py` (no variable writes), and every `gh variable set CI_RUNS_ON` writer (`delivery_ci_setup.py`, `delivery_runner_pool.py`): all use `json.dumps`, so no empty or non-JSON value. The ci.yml templates read it with `fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"')`. No change made to the writers, so no writer test was added.

## Tests
- `python3 -m unittest test_dl249_join_conflicts_held_runs` (4 tests): OK.
- `python3 tools/test_delivery_gate.py --no-mutants -k join`: 99 checks, 0 failed.
- test_watch, test_dl225, test_dl111, test_dl128, test_dl197: 104 tests OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- docs_check: only W1 (docs/work report, expected on a branch).
- spec-lint `areas=delivery`: run 43098373446 cancelled (held); run 43101111076, 10 minutes later, also cancelled mid-run (a train's CI, DL244-integration, was queued; the watcher holds branch runs). Its only real failure was docs check W1 (the report). No job failed on code. CI never finished clean.

## Follow-ups
- Re-dispatch spec-lint (areas=delivery) when no train CI runs.
- `docs_check` M1 wanted a note for the delivery-speed spec; the commit says `Docs: none`.

NOT READY
