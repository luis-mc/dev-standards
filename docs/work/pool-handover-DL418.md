# Runner rules removed from the delivery plugin (DL418)

The delivery plugin manages no runners. These rules left it in DL418. The runner pool project may take them up.

## DL-50: heavy jobs

- Run one heavy job at a time on a machine.
- A heavy job yields to release CI: it waits while a train's CI runs.
- A heavy job pauses the local runner when it starts and resumes it when it ends.
- The old code was `runner_plan.py run` (the `heavy-job` wrapper). It wrote `jobs[]` and `runners[].paused_by` to the ledger.

## DL-51: no extra CI runners, memory and CPU floor

- Never add CI runners on the owner's PC.
- Keep memory at or below 85 percent and CPU at or below 60 percent overall.
- The old code weighed free memory against running heavy jobs.

## Also removed with them

- DL-09: check that an online runner carries every label CI needs (`runner_health.py`, run by join and ci_watch).
- D6a: report an offline runner, repair it with `runners[].repair`, retry every 5 minutes, re-run wanted failed CI runs.
- Ledger fields `jobs[]`, `runners[]` and `paused_by`, and the ledger ops `job`, `runner` and `runners`.
- Config keys `local_runners`, `runner_plan.retry_seconds` and `runner_plan.report_command`.

## Kept in delivery

- The watcher's `runner_plan.cancel_replaced_runs` and `runner_plan.hold_dependabot_during_train` flags. They act on CI runs, not runners.
- The config `runners` list (CI Option 1) as a description of the project's CI; nothing in the plugin repairs those runners now.
- ci_watch warns once when a job is queued over 10 minutes. It does not look at runners.
