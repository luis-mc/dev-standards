---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
ci_watch.py exits 5 on every give-up path (gh failed five times in a row) and pins the repository at start, so a removed working directory cannot turn into a pass.
