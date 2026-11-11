---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

join.py creates a new `--into` branch, strips a leading remote name from branch arguments, defaults `--into` to `<first task id>-integration`, and resolves a Cargo.lock conflict with cargo. The ready-PR guard names the `<task>-integration` convention.
