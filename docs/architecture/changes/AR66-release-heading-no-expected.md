---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
A release with no Expected and no timed phases is headed `RELEASE-<n> · not scheduled`, so `task-add --release --status "To do"` without `--expected` is no longer refused by the R5.46 check. The heading has no stray whitespace, and `check` compares both sides with whitespace collapsed.
