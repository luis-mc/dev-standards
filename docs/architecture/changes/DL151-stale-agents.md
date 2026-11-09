---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL151: `delivery_ledger.stale_agents` now reads the project record (`registry.json` in the artifacts record folder) and returns the open agents whose task is Live, Built or Dropped. The session summary lists each one under "needing a check" with the fix, `agent-done`.
