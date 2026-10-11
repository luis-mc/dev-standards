---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
The shipped agents rule says agents test only what they touch: local suites for the files they changed, no CI runs on agent branches unless a change behaves differently on Linux, and the ready PR's CI as the one full run; a join skips the gate when the joined tree equals a branch head whose gate result it already trusts.
