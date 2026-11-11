---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

DL215: the runner-pool image keeps Node LTS and corepack at /opt/node on PATH, so ts CI jobs find `corepack`.
