---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
A failed gate setup step now names two common causes: a stale lockfile, and an install killed for memory (exit code 137). Exit code 137 prints the memory sentence first. The unfrozen-install rule is unchanged. The pool supervisor builds container paths with posixpath. Two pool sizing tests no longer depend on the pool floor, and the pool tests run on Windows.
