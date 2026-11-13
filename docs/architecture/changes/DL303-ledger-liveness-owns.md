---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
agent-check takes an agent's liveness from its branch's last commit and falls back to the run's last_event_at; the stop hook uses the same value. agent-eta warns when a brief's owns overlaps a running or unjoined agent.
