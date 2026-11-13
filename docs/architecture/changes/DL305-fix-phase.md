---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: minor
---
`--phase` accepts `fix` as a fifth phase name for a fix round after a red CI. `ci` and `fix` may repeat, so a release can run agents, join, ci, fix, ci, merge. The timeline shows `fix` as "fix round". Expected stays the end of the last phase.
