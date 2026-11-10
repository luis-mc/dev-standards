# DL181 CI rerun first (in progress)

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

(in progress)
