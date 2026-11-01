---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
agent_ci.py names each skipped branch with its reason and reports a push the pre-push guards refuse as a failing branch with the guard's lines.
