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
- Step 4 done: `enforcement.mode` (warn = systemMessage, nothing blocks, also for PreToolUse denies), `block_ceiling` (replaces the fixed 3 in `hooklib.block_decision`/`hook_stop.py`; `BLOCK_LIMIT` stays only as the default), `log_every_block` -> `.delivery/blocks.log` (`time<TAB>hook<TAB>rule<TAB>message`, hook `stop`|`pre-tool`).
- Step 5 done: `delivery_config.load_tz` raises with the fix when zoneinfo cannot load a zone (UTC needs no database); `delivery_ledger.owner_tz` still falls back to UTC so the ledger works, but warns once on stderr; SessionStart adds the warning to its context; `delivery_doctor.py [self-check] [--root] [--json]` checks config valid, gh signed in, tz loads, hooks registered (hooks.json + plugin enabled in project/user settings), ledger writable.
- `heavy_jobs_yield` / `heavy_local_jobs_yield` and top-level `train_branch_re` fallback implemented in `runner_plan.py` (the tooling copy), with a scenario in `tools/test_delivery_runner.py`.
- Docs: DELIVERYSPEC section 6, new `claude/plugins/delivery/README.md`, repo README, tooling README, claude-setup `delivery-config.json` template (new keys at their defaults; validates clean).
- Version: change note `docs/specs/changes/DS72-delivery-config.md` (minor). Per the repo convention a feature branch never edits `plugin.json`; the fold on the integration branch takes luismc-delivery 0.1.0 -> 0.2.0 (`change_notes.py fold --dry-run` confirms).

## Checks run
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests`: 94 tests, OK (was 62; +21 config/watcher, +11 doctor).
- `python3 -I tools/test_delivery_hooks.py`: 44 passed (was 40; +4 enforcement).
- `python3 -I tools/test_delivery_runner.py`: all passed (+1 scenario).
- `tools/spec_check.py`: 0 errors, 0 warnings. `change_notes.py check`: ok; `fold --dry-run`: 0.1.0 -> 0.2.0.
- Not run locally: `test_rule_tags.py`, `test_ci_areas.py`, `test_delivery_ci.py` (the repo's session guard refuses heavy suites locally; CI runs them; no rule file or ci_areas input was changed).

## Not done / notes
- Validated against a read of the comics config, not a live install. In this container `gh` is not signed in, so `delivery_doctor.py` on the comics checkout reports gh and hooks FAIL, as designed.
