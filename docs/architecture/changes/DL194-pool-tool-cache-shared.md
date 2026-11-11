---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL194: `ci_tool.py` makes cache folders `0777` in a world-writable cache root and falls back to `~/.cache/ci-tools` when a version folder is not writable. Any pool agent user can now fetch any tool.
