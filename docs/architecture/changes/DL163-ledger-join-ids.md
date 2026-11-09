---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL163: two releases on one day no longer share a train id. `link` makes a new row with a free id when no open row has the PR's branch, join-created rows take the next free id, the duplicate guard counts copies, and `show` warns about old duplicate ids.
