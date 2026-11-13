---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
`rust_ci.py` builds in `target/` when `ci_tool.py` is missing next to it, instead of crashing every gate command. (DL297)
