---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

A refused RemoteTrigger create or run (for example HTTP 429, no trigger id) no longer adds a running agent row. The post-tool hook records an `agent.launch_refused` event instead, so DL-41 does not block the retry.
