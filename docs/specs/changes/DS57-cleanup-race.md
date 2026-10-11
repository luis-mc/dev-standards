---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
`cleanup.py` treats a branch the train-cleanup workflow already deleted as done and updates a train release the workflow already created, instead of failing.
