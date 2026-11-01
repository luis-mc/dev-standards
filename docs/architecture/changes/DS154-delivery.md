---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
`delivery_watch.py` refuses a `runner_plan.script` that resolves outside the repository root; the README says the config, gate and smoke files are code to review before trusting.
