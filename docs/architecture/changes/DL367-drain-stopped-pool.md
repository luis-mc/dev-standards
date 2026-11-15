---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
A pool drain returns at once when the pool container is not running, instead of waiting 45 minutes for a supervisor that does not exist (runner-pool R5.64).
