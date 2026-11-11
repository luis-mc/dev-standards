---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The delivery installer keeps the project's artifact-prune workflow list on `update`. It applies one rule on overwrite, merge and conflict: the project's list wins, names the template added are appended once, names the project removed stay removed.
