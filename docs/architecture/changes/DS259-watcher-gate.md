---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The delivery watcher tests the merge result before it merges: `watcher.merge_result` is `warn` (default, one line) or `update` (`gh pr update-branch`); `ci_watch.py` prints a line for a green head that is behind its base (DS259).
