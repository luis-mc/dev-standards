---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

# DL306: cancel the rest of a red train run

`ci_watch.py` now cancels the other runs of a train head as soon as one job fails, and exits 1 at once. The push freeze reads the live runs, so it lifts when they end and the fix can be pushed. `--no-cancel-on-red` or `ci_watch.cancel_on_red: false` keeps the old wait. Agent branches are never cancelled.
