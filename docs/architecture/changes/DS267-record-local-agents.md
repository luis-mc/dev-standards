---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

Local agents with no delivery block get a ledger row (task read from the prompt) and are closed when finished; the Stop hook warns once about a Running task with no agent or CI (DS267).
