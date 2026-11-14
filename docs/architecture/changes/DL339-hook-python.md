---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The Windows runner hook wrappers and the host-load task use an all-users Python, never a per-user one (DL339); the doctor flags a per-user or missing hook Python.
