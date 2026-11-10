---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner-pool Dockerfile writes wrappers for the Wine entry tools in `/usr/local/bin` that unset `TMPDIR`, because Wine aborts with `free(): invalid pointer` when it is set.
