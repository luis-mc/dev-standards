---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

The load guard no longer sleeps 1 s to sample CPU: it takes CPU from the change in the raw counters since the previous cached sample, and falls back to the load average (or memory only) when there is none.
