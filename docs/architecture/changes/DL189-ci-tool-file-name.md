---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
ci_tool.py saves a kind file tool under its exact name in a per-platform folder, so tools that read argv[0] (rustup-init) work. Old cache files are ignored.
