---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---
The after-command hook takes the task of a `ci_watch.py` or `gh run watch` result from the watched head, not from the current checkout. A head on no task branch, or a task that is already Live, queues no event.
