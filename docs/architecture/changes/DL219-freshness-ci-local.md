---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---
The docs freshness check (T2) uses UTC dates of non-merge commits, so CI and local runs agree. It is skipped with an info line on a shallow clone.
