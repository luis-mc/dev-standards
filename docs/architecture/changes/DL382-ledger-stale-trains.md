---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The ledger guards against trains without a branch head, closes trains whose PR merged elsewhere or whose branch is gone, and has `close` and `close-stale` commands. The Stop hook prints one grouped line per rule and never tells a PR-less train to merge.
