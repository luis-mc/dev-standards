---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

The runner-pool image puts /opt/node/bin on PATH before the step that runs corepack enable, so the image builds again (DL220 failed with exit 127).
