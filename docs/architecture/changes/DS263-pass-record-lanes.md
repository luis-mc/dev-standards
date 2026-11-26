---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

`pass_records.py` gets `to-result` (a lane result from a default-branch pass record) and `copy-to-main`; `lifecycle_release_check.py` accepts a record result only for the default branch and the same inputs key; the shipped ts `ci.yml` is unchanged and has no job that writes records (a project may call `copy-to-main` from its own workflow and grant `contents: write` itself) (DS263).
