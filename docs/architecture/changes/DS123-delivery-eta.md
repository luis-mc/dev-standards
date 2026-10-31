---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

The delivery block parser now reads the one-line `eta:` form from the brief template and splits `owns` on commas only. The ledger gains the `agent-eta` command that the Stop hook's DL-30 message names, with the agent's id in the message.
