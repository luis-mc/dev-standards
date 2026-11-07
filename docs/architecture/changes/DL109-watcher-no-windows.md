---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The delivery watcher opens no console windows on Windows: SessionStart starts it on a hidden console and every gh and git call passes CREATE_NO_WINDOW. A second watcher for the same root exits when a live one already runs (DL109).
