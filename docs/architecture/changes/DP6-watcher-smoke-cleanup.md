---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The watcher counts as dead after 20 minutes with no heartbeat and SessionStart restarts it. After a merge the watcher runs cleanup_command and smoke_command; if one fails it pushes no next train (DP6).
