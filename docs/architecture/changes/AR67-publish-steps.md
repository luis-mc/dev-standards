---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
AR67: `pending --refresh` now renders first, so the publish copy always matches a fresh render and `mark-published` no longer refuses right after a publish. The refusal also names the next command. AR68: the task-status-update skill now lists the `--phase` names: agents, join, ci, merge.
