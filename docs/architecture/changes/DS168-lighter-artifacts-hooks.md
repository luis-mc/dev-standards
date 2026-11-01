---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
The artifacts end-of-turn hook now reads `pending` in the same process instead of starting a second Python process. The session-start hook asks `gh` for fewer pull requests (two per open task, 20 to 200) and does not call `gh` when no task is Running, Waiting or To do.
