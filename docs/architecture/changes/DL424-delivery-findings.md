---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Delivery: `cancel_old_run.py --pr N` cancels a train's old run so the freeze lets a fix push through (DL424); docs and config pushes skip typecheck and lint (DL425); the e2e push check reads the gate result from any worktree of the repository (DL426).
