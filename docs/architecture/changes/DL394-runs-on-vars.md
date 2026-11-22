---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: DELIVERYSPEC
change: minor
---
The delivery workflow templates pick their runner from RUNS_ON_<OS> first, then the old CI_RUNS_ON[_WINDOWS], then the GitHub-hosted default. The setup writes RUNS_ON_LINUX; the doctor reports which variable each OS resolves to and warns when old and new differ.
