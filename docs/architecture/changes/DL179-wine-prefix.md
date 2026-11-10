---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The pool supervisor prepares a Wine prefix per agent user at container start (only with the windows-packaging layer) and exports POOL_WINE_PREFIX to each runner.
