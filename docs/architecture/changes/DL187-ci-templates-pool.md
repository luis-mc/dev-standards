---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The rust and ts CI templates skip the postgres service on a pool runner and load the pool database env; the rust migrate and test steps run only for what the workspace has (DL187).
