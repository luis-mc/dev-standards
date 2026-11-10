---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The pool setup, `apply` and the doctor now share one set of rules: pool agent name, expected `CI_RUNS_ON` (with the pool label), template version (`pool-version.json`) and the layer check on the running container's image. The doctor is clean right after a pool setup.
