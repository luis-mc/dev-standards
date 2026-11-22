---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

DL397: `update` merges `gate.json` by step name and keeps project steps; doctor `gate-steps` check; e2e push check hints instead of blocking when gate.json has no e2e step; template test steps carry a per-test timeout.
