# DS68: delivery ledger, recorder and watcher

Branch `DS68-delivery-ledger` (from `DS67-delivery-integration`). Contract: `docs/specs/delivery/DELIVERYSPEC.md` sections 2, 4(a), 5 (D5, D6 binding).

## Plan (pushed after each step)
1. Ledger module + CLI + JSON Schema, plugin.json (no hooks.json: DS69 owns it).
2. PostToolUse/PostToolUseFailure recorder + UserPromptSubmit answer marking.
3. Watcher (injectable shell, --once, --dry-run).
4. Best-effort ledger calls in join / ci_watch / cleanup / runner_health.
5. Tests, repo checks, draft PR.

## Log
- Read the spec, artifacts plugin layout (`hook_after_command.py` pattern: never block, exit 0) and the four delivery scripts.
- Ledger module, schema and recorder written (steps 1-2).
- Watcher written (step 3).
- Call-ins added to join/ci_watch/cleanup/runner_health via delivery_common.ledger_record (step 4).
- Tests (step 5): `python3 -m unittest discover -s claude/plugins/delivery/tests` -> 62 tests OK (ledger locking/atomicity, event cap, phase derivation, schema; recorder for Bash push/PR/merge/install/ci_watch, Agent, RemoteTrigger, Artifact, AskUserQuestion, UserPromptSubmit, process-level exit 0 and < 1 s; watcher merge-at-green on current head only, never with a hold, never `--auto`, push next train + ready PR, cancel superseded, hold + rerun dependabot, agent stalled at > 2x work, runners/installs/heartbeat; all gh/git mocked).
- Repo checks run on this branch: test_delivery_ci (60 passed), test_delivery_cleanup (298 checks, 0 failed), test_ci_areas, test_rule_tags, test_model_profiles: all pass.

## Decisions and notes
- No `hooks/hooks.json` and no marketplace/README entry (DS69 / DS71 own them). Hook registration will be: PostToolUse + PostToolUseFailure `Bash|Agent|Task|RemoteTrigger|Artifact|AskUserQuestion` and UserPromptSubmit, all `hook_post_tool.py`.
- The recorder is a no-op in a repo without `.delivery/`; switch `CLAUDE_DELIVERY_HOOKS=off`.
- `delivery` block format (in an agent/routine prompt): lines `task`, `branch`, `where`, `model`, `effort`, `basis`, `owns` (comma list), `setup`, `work`, `checks` (minutes), optional `total`.
- Watcher config keys (`.delivery/config.json`): `base` (default main), `watch_interval`, `install_state_files`, `local_runners`, `train_branch_re`, `eta_required`. Added `held_runs` (top level) and `created_at` (train) to the schema for D6 and phase derivation.
- Held (cancelled) non-train runs are re-run once no train is in `pushed`/`ci`; with several joined trains in a row they wait for the last one.
- Call-ins go through `delivery_common.ledger_record`, which finds the module on sys.path, `$DELIVERY_PLUGIN_DIR/scripts` or `~/.claude/plugins/**/delivery/scripts`; no-op otherwise. runner_health records an event only (it sees labels, not runner names; the watcher writes `runners[]`).
- Cloud routine status needs a tool the script cannot call, so `routine_fetcher` is an injectable seam that defaults to none.
- The PR ledger-file state `ci`-from-`ci_watch` matches the train by head sha, else the first pushed/ci train.
