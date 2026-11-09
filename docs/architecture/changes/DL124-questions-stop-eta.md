---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---

The clarifying-questions stop hook now counts an agent in .delivery/ledger.json that has an ETA (agent-eta) and is not finished (no agent-done) as a running agent, so parked questions are allowed while it runs. It reads the ledger defensively: a missing or bad file adds no agents. When such an agent is due within 60 minutes, the hook allows the stop and says questions wait for that agent's report.
