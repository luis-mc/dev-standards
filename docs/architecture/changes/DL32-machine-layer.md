---
spec: docs/architecture/DELIVERYSPEC.md
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL-79 now also takes a CI slot from the machine queue and has a job-completed hook; new DL-90 (machine config, CI slots, one queue, slot log, host load file, the slot wait that starts the fallback, doctor `machine` check) and DL-91 (local heavy work limit and cloud CI session limit). A project can lower a machine limit and never raise it.
