---
plugin: claude/plugins/transcript-folds/.claude-plugin/plugin.json
change: patch
---

Fixes from the plugin review. PowerShell edits are counted like Bash. A shell call with no result yet, or with unreadable edit data, keeps the engine row. Row widths ignore colour codes, count tabs, emoji with a variation selector and combining marks correctly. The first error line falls back to stdout when stderr is blank. The session tally counts a Windows file once whatever its slashes or case, and UNC paths compare without case. The spec test command now runs on Node 22.
