---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
The Stop hooks read only the current turn from the end of the transcript, in 1 MiB blocks, and allow the stop when the turn is over 32 MiB (DL208).
