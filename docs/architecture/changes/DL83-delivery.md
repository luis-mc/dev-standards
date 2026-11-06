---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The pool supervisor now gives each agent a CI_MAX_PARALLEL equal to the pool's CPU count divided by the number of agents, at least 1, and logs it. Before, every job saw the whole pool's CPU count, so two busy agents could run too many test workers and be killed for memory. The doctor now warns when POOL_MEM divided by the agent count is under 4 GiB.
