---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
`agent_ci.py` default marker accepts a list bullet and a ticked checkbox before `CODE DONE`, so a checklist report starts the CI run. An unticked box does not count.
