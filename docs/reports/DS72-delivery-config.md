# DS72: luismc-delivery 0.2.0 (config schema, watcher obeys config, block log, doctor)

Task CO176. Branch `DS72-delivery-config` from `main`. Contract: `docs/specs/delivery/DELIVERYSPEC.md` (D1-D9, D6a).

## Plan
1. Report (this file).
2. Config schema (`references/config-schema.json`) + `delivery_config.py validate`, docs, tests. Unknown keys warn.
3. Watcher reads and obeys `watcher.*` and `runner_plan.*`; launches `runner_plan.py runners` itself (D6a).
4. `enforcement` (`mode`, `block_ceiling`, `log_every_block` -> `.delivery/blocks.log`).
5. tzdata: loud failure + `delivery_doctor.py`.
6. Docs, change note (minor: 0.1.0 -> 0.2.0), repo checks, PR.

## Source config
comics-organizer `CO159-delivery-setup` `.delivery/config.json` read. Key-name differences from the task text, all accepted (aliases, 0.1.0 names kept):
- `watcher.merge_method: "merge"` (task) vs `watcher.merge_flag: "--merge"` + `never_auto_merge: true` (real file): both accepted; `--auto` is rejected by the validator and never run.
- `runner_plan.heavy_jobs_yield` (task) vs `heavy_local_jobs_yield` (real file): both accepted.
- `watch_interval` / `watcher_interval_s`, `local_runners`, `base`, `eta_required`: present in the real file, in the schema.

## Progress
- Step 2 done: `references/config-schema.json`, `scripts/delivery_config.py validate` (`--root`, `--config`, `--json`, `--strict`; exit 0 valid, 1 errors, 2 unreadable), typed accessors. Unknown keys warn, `_` keys are comments. The comics config and the claude-setup template validate with 0 errors, 0 warnings.
- Step 3 done: watcher reads `watcher.push_trains|open_prs|merge_on_green|manage_runners` and `runner_plan.cancel_replaced_runs|hold_dependabot_during_train`; merge re-reads the PR head and merges only if unchanged since the green run (`gh pr merge N --merge --match-head-commit SHA`, never `--auto`); the watcher spawns `runner_plan.py runners` on its loop and relaunches it on exit (D6a). All flags default true = 0.1.0 behaviour. `heavy_jobs_yield` is obeyed where the wait happens, in `runner_plan.py run` (next).
