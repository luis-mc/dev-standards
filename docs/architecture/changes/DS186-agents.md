---
plugin: claude/plugins/agents/.claude-plugin/plugin.json
change: patch
---

The architect agent now lists Bash in disallowedTools, so it cannot change files through a shell. This is the smaller change: the spec already says the agent is read-only.
