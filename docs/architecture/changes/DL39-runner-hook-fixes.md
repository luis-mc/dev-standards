---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Runner hooks: Windows wiring uses the `.ps1` wrappers and the `.cmd` wrappers are removed; the shard of a job is `DELIVERY_SHARD` or else the job key; the `ci-wait` marker loads the plugin's own `ci_fallback.py` and logs why it is skipped; the doctor fails a `.cmd` hook and warns when the runner account cannot push.
