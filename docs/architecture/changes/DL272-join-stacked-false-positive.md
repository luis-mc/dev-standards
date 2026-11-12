---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

DL272: join.py no longer refuses a stacked branch up front. It tries the merge and refuses only on a real conflict. Siblings cut from one older head are not stacked. The conflict report never prints an empty file list.
