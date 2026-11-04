---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The pool setup command now measures the pool cap on the machine (flags only override), uses the repositories detect found when `--repos` is empty and names them in the plan, and checks each step with that step's own check. The plan prints first for `pool-run`.
