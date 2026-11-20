---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
delivery_watch cancels a superseded run only when the newer head has its own run, is not a bot push, and the older run has no failed job (unless ci_watch.cancel_on_red); skips are logged as ci.cancel_skipped.
