---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---

The delivery log says its times are UTC (headers and footnote), and CI start is the first run on the ready pull request's branch since the pull request was created, so earlier fix-forward rounds are no longer counted as waiting.
