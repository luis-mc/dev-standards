---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

The runner gate (`runner_load_gate.queue_wait`) no longer waits forever when its own ticket is missing from the queue list. It logs `own ticket was gone; queued again`, writes the ticket again with the same queue time and goes on. Tests that call `R.main` now set a short wait and poll, so a regression fails fast.
