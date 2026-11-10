# DL181 CI rerun first

## Base check

`git fetch origin main && git checkout -B DL181-ci-rerun-first origin/main`, then `git merge-base --is-ancestor 8d7358b1 HEAD`: succeeded (ANCESTOR_OK). Base 2b5d86b.

## Design

Rule: on a new push, the jobs that did not pass on the previous head run first; the jobs that passed come after. A first run behaves as today.

GitHub `needs` is static, so one run cannot reorder the same jobs.

| | (a) second wave of the same jobs behind a barrier | (b) plan holds the passed jobs back, a last job dispatches them | (c) wait inside the later jobs / reorder by queue |
|---|---|---|---|
| Runs | one | two (the second is a `workflow_dispatch` of the same file) | one |
| Runner minutes, one runner | the job bodies exist twice; about 3 long jobs duplicated, large file | no extra minutes; the held jobs run once, after the first set | a waiting job holds the only runner: deadlock |
| A failure in the first set | shows at once; the barrier job is skipped, the second wave never starts | shows at once; the dispatch job does not run | not applicable |
| First run | both waves would run; needs care to avoid double runs | plan holds nothing; same graph, same ifs | n/a |
| Project that does not opt in | ci.yml carries 3 extra copies of every expensive job | only an extra plan step, an empty `held` output and one cheap last job that is skipped | n/a |

Pick (b). It is the only one that keeps the file small, adds no waiting job and starts with a failure the moment the first set fails. Cost, stated plainly: the held jobs report as skipped (green) in run 1 until run 2 reports them, so the PR is not safe to merge until run 2 ends. The `rest` job writes the run number in the summary, and `ci_watch.py` already waits for every run of the head. Follow-up: a commit status that stays pending until run 2 ends.

Opt-in key: `rerun_first: true` in `scripts/delivery/ci-areas.json`. That file already drives the plan job (`area_select.py` reads it), so no new file and no change to `.delivery/config.json`, which the CI runner does not read. The script reads the key itself; the workflow step runs always but the script prints `rerun=false` when the key is off.

Held jobs: `verify`, `integration`, `e2e-shard`. The aggregator `e2e` always runs.


### Design change while building

The first wiring added a `rest` job and a hold clause in the job `if:` lines. `tools/test_delivery_ci.py` (`workflows_conform`) refuses both: one job per family, an exact decide-aware `if:`. So the final wiring adds no job and no `if:` change:

- The plan outputs `integration` and `e2e` turn `'false'` for a held job (a planned skip the jobs and the `e2e` aggregator already handle).
- The dispatch is the second-to-last step of the `e2e` aggregator (it needs `plan`, `verify`, `integration`, `e2e-shard`). It runs only when the first set passed and `rerun` is true. `e2e` gets `actions: write`.
- `verify` is not held: it has no `needs: plan`, and giving it one would change the graph for every project.

## What changed

- `claude/plugins/delivery/templates/shared/scripts/delivery/ci_rerun_first.py` (new). Opt-in key `rerun_first` in `scripts/delivery/ci-areas.json`: that file already drives the plan job, and `.delivery/config.json` is not read in CI. Previous all green: `rerun=false`, `first=[]`. Every holdable job in the first set: `rerun=false` (nothing to hold). `--only` is the second run.
- `claude/plugins/delivery/templates/ts/.github/workflows/ci.yml`: `workflow_dispatch` input `only`; plan step `rerun`; plan outputs `rerun`, `held`, and held-aware `integration`/`e2e`; dispatch step in `e2e`. Job set and `needs` unchanged.
- `claude/plugins/delivery/tests/test_dl181_ci_rerun_first.py` (new, 15 tests).
- `docs/features/delivery/spec.md`: R5.52. Feature note `docs/features/delivery/changes/DL181.md`. Change note `docs/architecture/changes/DL181-ci-rerun-first.md`.
- Paths: `tools/ci_areas.py` maps `claude/plugins/delivery/` to the `delivery` area, so the new script and test are covered; no change to `.claude/suites.json` (the delivery tests dir is run by spec-lint through `unittest discover`).

## Tests

- `python3 -m unittest test_dl181_ci_rerun_first test_dl147_workflow_needs test_dl116_fetch_check test_ci_options` (in `claude/plugins/delivery/tests`): 65 tests, OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed (it failed twice before the redesign above).
- `python3 claude/plugins/docs/scripts/docs_check.py`: one error, W1 (this report under docs/work, expected). M1 for the delivery-speed spec is answered by `Docs: none` in the second commit message.
- `gh workflow run spec-lint.yml --ref DL181-ci-rerun-first -f areas=delivery,docs`, run 42914080375, every job ended:
  - success: which areas, delivery ledger/recorder/watcher/hooks, setup preflight, train cleanup, packaged-program smoke, area mapping, CI scripts and workflow templates, branch gate and trust rule, artifact pruning, runner plan, change notes enforced and folded, docs plugin, delivery scripts/CI templates/cleanup/prune/change notes.
  - skipped: change notes, change notes folded, transcript folds, branch gate shard matrix, specs/templates/AUTHSPEC, model profiles, artifact renderer.
  - failure: docs check, only W1 (this report).

Not run: the new workflow path on a real pull request (no PR may be opened); the job text and the script are tested, the live dispatch is not.

## Risks

- The held jobs read as skipped (green) in run 1 until run 2 ends. A merge must wait for run 2. The dispatch step writes this in the job summary.
- Run 2 runs `verify` again (it is never held). It is cheap relative to the held jobs.

## Follow-ups

- Same wiring for the rust, go and dotnet templates.
- `ci_watch.py`: wait for the dispatched run of the head before it reports done.
- A commit status that stays pending until run 2 ends.
- `agent_ci.py`, `ci_scope.py`, `area_select.py`, `ci_skip_check.py`: no change needed now.
- `CONTRACT.md` table: add `ci_rerun_first.py`.
- Skip `verify` in run 2 (needs `needs: plan` on `verify`, a graph change).

## Branch head

Code head: 7a9e238 (the report commit follows it; the branch head is the commit after).

READY
