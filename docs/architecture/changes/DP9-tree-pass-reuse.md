---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
branch_gate.py skips the gate when the same git tree already has a pass record; pass_records.py accepts a "tree": true shard (DP9, R13.36).
