---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The watcher no longer closes an agent row on an in-progress `NOT READY` last line. A final `NOT READY` closes the row only after 10 quiet minutes on the branch. `agent-check --reopen` reopens a closed row.
