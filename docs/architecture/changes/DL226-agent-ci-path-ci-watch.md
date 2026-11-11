---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
agent_ci.py reads the agent report at docs/work/<TASK>/REPORT.md first, then docs/work/reports/<TASK>.md. ci_watch.py waits for all runs of a commit before it reports a failure, and never labels an in-progress job as failed.
