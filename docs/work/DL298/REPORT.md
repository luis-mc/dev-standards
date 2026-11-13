# DL298 report

Base check: `ci_state_from_runs`, `runs_for_commit`, `workflows_needed` present on origin/main.

## What changed
- `delivery_watch.py`: `runs_for_commit` keeps the per-workflow listing for configured workflows and adds one `gh run list --commit <sha>` without `--workflow`. Other workflows with a `pull_request` run on the head join the required set (logged once per train). Push, schedule and manual runs never count unless configured.
- Ready-time filter: last `ready_for_review` timeline event, else PR `createdAt`. Earlier runs are dropped. A draft PR is never green (`head_ci`, used by `pass_trains` and `_recheck_red`).
- `delivery_config.py` / `config-schema.json`: `watcher.ignore_workflows` (names or files, default empty).
- Docs: DELIVERYSPEC `watcher.ci_workflows` text, feature spec R5.7, feature note, change note.
- Tests: new `test_dl298_head_runs.py` (11 tests). Edited existing fakes in `test_watch.py` and `test_config.py` for the extra calls.

## Tests
- `python3 -m unittest discover -s tests` in the delivery plugin: 1632 run, OK (4 skipped).
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only the expected W1 on docs/work.
- spec-lint dispatch 1: failed in `test_merge_waits_when_head_moved_since_green_run` (fixed). Dispatch 2 (run 43438752632): every job passed except `docs check` (W1 expected on a branch). Its log could not be read (gateway 502).

## Follow-ups
- The red-train recheck now costs two `gh pr view` and two `gh run list` calls per cycle (was one each).
- An ignored file entry matches by the file's `name:` line; other tools should list the workflow name.

Branch head SHA: see `git rev-parse` of the branch tip after this commit.

READY
