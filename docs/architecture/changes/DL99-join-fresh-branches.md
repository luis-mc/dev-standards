---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The cleanup that `join.py` runs first now keeps fresh local branches and their worktrees. `join.py` passes its start time to `cleanup.py --local --keep-fresh-since`. A branch is kept when its first commit outside the default branch (or, with none, its tip commit or creation in the reflog) is newer than that time, or when the ledger shows a running agent on it. Each kept branch prints one `cleanup: skipped` line with the reason. A missing or unreadable ledger skips only the agent check.
