---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The pool container recreate (refresh, drain, cap change) counts only runners in the container; a busy Windows service runner no longer blocks it (DL354).
