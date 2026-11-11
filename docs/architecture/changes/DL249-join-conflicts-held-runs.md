---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

`join.py` always lists the conflicting files and rebuilds conflicts that are only in generated docs. The watcher records a held CI run as `held` and prints a clear line.
