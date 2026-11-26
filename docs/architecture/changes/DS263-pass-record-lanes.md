---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

`pass_records.py` gets `to-result` (a lane result from a default-branch pass record) and `copy-to-main`; `lifecycle_release_check.py` accepts a record result only for the default branch and the same inputs key; the ts `ci.yml` copies the pull request's records to main in its own `copy-records` job (write permission on that job only) when the push is skipped (DS263).
