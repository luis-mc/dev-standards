---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: minor
---
The design-system guards now fail a numbered version without a complete approval record, an enforced version without an implementation approval, and a stale gallery (a failure on release branches, a warning on task branches). `design_system.py verify` runs the checks, and `approve-implementation --as-live` records a version that is already live.
