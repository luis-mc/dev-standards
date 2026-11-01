---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
The artifacts end-of-turn hook now reads `pending` in the same process instead of starting a second Python process. The session-start hook does not call `gh` when no task is Running, Waiting or To do.
