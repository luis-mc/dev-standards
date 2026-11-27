---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
task: DS302
---
Hook launchers skip a `python3` under WindowsApps (the Windows app alias, which can hang or refuse to run) and use `python` instead, so hooks no longer time out on such a PC.
