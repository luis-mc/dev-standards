---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
`scripts/plan_rows_check.py` lists numbered plan rows and audit findings in a report that no registry task mentions, and the `task-add` skill says each becomes a task in the same turn with the key `<tag>#<id>` in the detail. The Stop hook (`hook_end_of_turn.py`) runs the same check for any report under `docs/work/` written in the turn and blocks the end of the turn while rows are untasked (owner decision D238).
