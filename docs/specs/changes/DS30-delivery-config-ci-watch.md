---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The config schema lists `ci_watch.post_run` and `ci_watch.post_run_timeout_seconds`, read by `ci_watch.py`, so a config using them no longer warns about unknown keys.
