---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
agent-check takes --note; agent-done and agent-check on a closed agent exit 0; the pre-push hook skips the node checks for a push with no JS file when node_modules is missing.
