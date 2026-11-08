---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL118: session start now tells the session when an old delivery_watch cannot be stopped (access denied), with the pid and the command to run from an elevated shell, and still starts the installed watcher. The liveness check on Windows uses OpenProcess, so a dead pid is not reported. Watcher rows with a dead pid and a heartbeat over 24 hours old are pruned from the ledger by the watcher heartbeat and at session start.
