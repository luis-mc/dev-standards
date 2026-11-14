---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner gate writes no ci-wait marker, and runs no git, when the project has no `ci.fallback` in `.delivery/config.json`.
