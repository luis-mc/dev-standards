---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
ci_watch.py no longer reports green for a commit whose only run is a push run with every job skipped when that commit is the head of an open pull request: it waits for the pull_request run (exit 4 "no real run yet" on timeout) and is green only when every executed run succeeded and at least one executed.
