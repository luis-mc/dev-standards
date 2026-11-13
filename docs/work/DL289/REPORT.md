# DL289 report

Base check: origin/main has `refused: pool runner busy` in delivery_runner_pool.py and hooks/job-started.sh. OK.

## What changed
- `pool-refresh --yes`: copy files and write `.env`, then `docker compose build` while the old container serves jobs.
- Then drain: write `<machine>/pools/<pool>/drain`; wait for `drained` (poll 5 s, `--drain-timeout`, default 2700 s).
- Then the GitHub busy check again, `docker compose stop pool`, remove the drain file, `up -d --no-build --force-recreate pool`.
- Timeout: remove the drain files, print `refused: drain timed out, busy: <agents>`, container untouched (image stays built; files stay written; rerun is safe).
- `--force`: no drain, warns, recreates.
- No file or `.env` change and the container already runs the tagged image: no drain, no recreate.
- `pool_supervisor.py`: drain mode. Idle listeners stop and stay stopped. Busy ones (marker newer than 6 h) finish, then stop. It writes `drain-busy` and `drained`. Listeners restart when `drain` goes.
- Hooks: job-started writes `/agents/<slug>/.job-running` (slug from the TMPDIR parent), job-completed removes it. Neither can fail a job.
- Docs: runner-pool spec R5.10, R5.13, R5.15 sentences; feature note; change note.
- A SIGTERM to a runner listener with a job cancels the job, so `stop_grace_period` alone does not protect it. Documented in R5.13.
- Existing tests updated for the new order: dl103, dl162, dl165 (two compose-recreates-in-build cases removed; that no longer exists).

## Tests
- `python3 -m unittest test_dl289_refresh_drain` (13 tests): OK.
- Pool and hook tests (`discover -p "test_*pool*.py"`, hook tests): 374 + 29 OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 on docs/work (expected on a branch).
- spec-lint.yml (areas=delivery) run 43356925528: all delivery jobs success; "docs check" failed only on W1.

## Try it on a real pool
Run `delivery_ci_setup.py pool-refresh --yes` while a job runs. Expect the build, then a wait, then the recreate after the job ends. Check `<machine>/pools/<pool>/drain-busy` during the wait. The new supervisor and hooks reach the container only through this refresh, so the first refresh from the old files still uses the old hooks: the marker does not exist yet, so every agent counts as idle. Run one refresh to install them; use the next one for the drain.

## Follow-ups
- The first refresh cannot drain (see above); the GitHub check is the only guard then.
- A listener can take a job between the marker check and the stop (a window of seconds); the GitHub check cannot see it.
- `apply_cap` (cap change) still recreates with no drain.

Branch head: see `git rev-parse origin/DL289-refresh-drain` (code at 5989ca0).

READY
