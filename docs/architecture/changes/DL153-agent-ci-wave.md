---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL153: `agent_ci.py` now starts CI only for agents that are open in the ledger, or for the tasks and branches named with `--task` and `--branch`. `--all` keeps the old scan of every branch under the prefix. The task id is read from the branch name after the prefix's last `/`, so a prefix like `claude/RS` works. The script help and the delivery spec (R13.77) say that `gh run cancel` can stall on a queued run and the force-cancel API works.
