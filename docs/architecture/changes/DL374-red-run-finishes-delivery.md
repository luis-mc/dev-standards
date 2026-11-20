---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

A red release CI run finishes: the pre-tool hook refuses to cancel it while jobs still run (DL-97, D105), and `cancel_joined_runs.py` skips it. The doctor warns on fail-fast in pull-request workflows (DL-98, D104).
