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
