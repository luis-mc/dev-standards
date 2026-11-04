---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
New `ci_runs.py collect` writes `.delivery/ci-runs.json` (GitHub runs, step times, slot wait), and `delivery_watch.py` refreshes it each tick, at most once a minute (owner decision D48).
