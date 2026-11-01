---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL-06 judges only the newest run of each workflow on a PR head and treats a skipped run (such as a draft-PR skip) as passing; failure, cancelled and timed_out runs still block.
