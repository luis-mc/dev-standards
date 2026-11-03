---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Option 4 fallback launchers in the delivery templates: `fallback_launch.py` (cloud and hosted launchers, `sweep`, `launch`), `fallback_run.py` (claim last, then the shard), the hosted workflow `ci-fallback.yml`, the hourly routine template, and a fallback hook in `ci_watch.py` (`--no-fallback` turns it off).
