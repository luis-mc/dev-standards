---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

New config keys `watcher.infra_retry` (default false) and `watcher.infra_retry_patterns`: the watcher re-runs the failed jobs once after an infrastructure failure and records a `ci.retry` event (DS260).
