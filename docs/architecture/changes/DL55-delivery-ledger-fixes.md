---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The delivery ledger no longer replaces an unreadable file with an empty one: it keeps a copy next to it and stops with an error. `agent-eta` now takes any open agent (queued, running, pushed or stalled) by routine id, run session id or task, and `--root` works after the subcommand. Two rows for one launch (the routine id and the run session id) are merged into one row on the next ledger write.
