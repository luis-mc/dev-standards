---
change: minor
task: DP6
---
R5.69: the watcher counts as dead after 20 min with no heartbeat and SessionStart restarts it; after a merge it runs cleanup_command and smoke_command and stops the next push if one fails.
