---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/architecture/DELIVERYSPEC.md
change: minor
---
The delivery plugin no longer enforces runner rules, because it manages no runners. DL-09, DL-50 and DL-51 are removed rows. `runner_health.py`, the watcher's runner pass, and the `jobs[]` and `runners[]` ledger fields are gone. ci_watch still reports a job queued over 10 minutes, without a runner lookup.
