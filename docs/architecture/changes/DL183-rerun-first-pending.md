---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL183: with `rerun_first`, the plan job sets the commit status `rerun-first/held` to pending when it holds jobs. The second run closes it (success, failure or error); a failed first set sets failure. `ci_watch.py` waits for the second run while the status is pending. Projects that do not opt in get no status.
