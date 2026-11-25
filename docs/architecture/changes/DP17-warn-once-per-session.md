---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Warn report counts a rule once per session: blocks.log warn lines carry the session id, delivery_report.py dedupes by rule and session (DP17).
