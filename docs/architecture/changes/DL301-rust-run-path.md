---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
`rust_ci.py run` resolves the program on the job PATH it passes, so a tool found only there no longer fails with WinError 2 on Windows. (DL301)
