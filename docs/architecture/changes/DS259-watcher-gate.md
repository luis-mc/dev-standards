---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The delivery watcher tests the merge result before it merges: `watcher.merge_result` is `warn` (default, one line) or `update` (`gh pr update-branch`); `ci_watch.py` is unchanged (DS259).
