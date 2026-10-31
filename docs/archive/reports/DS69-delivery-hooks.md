# DS69: delivery Stop, PreToolUse and SessionStart hooks

Status: done, draft PR to DS67-delivery-integration. Brief (b) of DELIVERYSPEC section 4 with the section 5 decisions.

## What was built (claude/plugins/delivery/, plugin luismc-delivery 0.1.0)
- `hooks/hooks.json`: Stop, PreToolUse (Bash|Agent|RemoteTrigger|AskUserQuestion|Write), SessionStart, PostToolUse and PostToolUseFailure (Bash|Agent|RemoteTrigger|Artifact|AskUserQuestion) and UserPromptSubmit, all `python3 ... || python ...`. The last three point at `scripts/hook_post_tool.py`, which DS68 writes (not in this PR).
- `scripts/hooklib.py`: config with safe defaults (`.delivery/config.json`), a read-only ledger adapter (schema 1, DELIVERYSPEC section 2; `delivery_ledger.py` is not used or created), clock seam, command tokeniser, block-once-per-fingerprint state with the 3-block ceiling (`.delivery/hook-state.json`).
- `scripts/hook_stop.py` (blocking, D3): DL-02, 03, 14, 18, 30, 31 (ETA clock time and dependency; tomorrow / next round / in the morning unless a computed past-midnight time is given), 32, 33, 63 (reads docs/artifacts/registry.json), 64 (config `train_label_re`, plus ledger ids and branches), Q-2 (closing list of questions). The reply text comes from `last_assistant_message` or the transcript.
- `scripts/hook_pre_tool.py` (deny with a one-line reason and fix): DL-05, 06, 07, 20, 23, 36, 37, 38, 41, 42, 53, 55, 73, 74, 75, D4, Q-3, Q-4.
- `scripts/hook_session_start.py`: ledger summary, catch-up of PRs gh reports merged but the ledger shows open (reported, not written), hourly check-in instruction, watcher start prompt.
- `tools/test_delivery_hooks.py`: 40 tests, fixtures only, gh stubbed through `DELIVERY_GH`, clock through `DELIVERY_NOW`.

## Decisions and limits
- Opt-in: no `.delivery/` folder (found upward from cwd) means no output from any hook. `CLAUDE_DELIVERY_HOOKS=off` and config `checks_off` switch checks off. Any hook error fails open.
- `no-tomorrow.mjs` was not in the repo or its history; the logic is implemented from the D9 rule. Retiring the user-level hook is left to claude-setup.
- DL-37 for a local Agent: the Agent tool has no effort field, so effort is read from an `effort:` line in the brief's fenced `delivery` block. DL-41 reads `owns:` from the same block.
- DL-06 compares `ci.head_sha` with `gh pr view` `headRefOid`; if gh is unavailable the head comparison is skipped but ledger CI success is still required.
- DL-23 denies `--no-frozen-lockfile` always, and an unfrozen install only when the command mentions a gate marker (config `gate_markers`).
- Not run locally: the full `ci-areas` suite (the repo's session guard refuses a full local run). The new test file maps to the `delivery` area in `tools/ci_areas.py`; the plugin path is not mapped there and falls through to all areas.

## Checks run
- `python -I tools/test_delivery_hooks.py`: 40 passed, 0 failed.
- `python -m compileall` on the scripts: clean.
