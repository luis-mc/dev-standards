---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL111: join.py no longer drops clean merges when a later branch conflicts. It aborts only the failing merge, goes on with the remaining branches, keeps every clean merge, and reports each conflicting branch with its files. With --push it pushes the clean merges and exits 3.
