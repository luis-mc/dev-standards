---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The artifact-prune template runs once a day and by hand, not after every workflow. Every job in the shipped workflow templates has `timeout-minutes` of 30 or less (G2).
