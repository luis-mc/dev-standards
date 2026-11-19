---
spec: claude/plugins/docs/references/artifactspec.md
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: minor
---
Full Progress is published once after a burst of record changes: a settle window (`full_progress.settle_sec`, default 60) in `pending`, `mark-published` and the end-of-turn hook, and an unchanged copy is not asked for outside the hourly fail-safe (R9.13, R9.14).
