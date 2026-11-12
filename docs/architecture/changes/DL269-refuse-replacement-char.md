---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---
`project_artifacts.py` refuses the replacement character U+FFFD in the free-text options of `task-add` and `set-task-status`, and `check` reports one already held in a task or content file.
