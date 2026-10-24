---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
The shipped ci_watch.py (tooling/shared/scripts/delivery) waits for the pull_request run instead of counting a fully skipped push run as success on an open pull request's head.
