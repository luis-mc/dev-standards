---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
ci_watch.py no longer reads `origin/HEAD` or the default branch as a feature branch, so a watch on a default-branch commit makes no train (R5.62).
