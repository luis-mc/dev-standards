---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
spec: claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md
change: minor
---
The shipped delivery scripts change: `cleanup.py --pr N` also removes every branch joined into the merged train (tip an ancestor of the merged pull request's head, no open pull request), and `join.py` skips the gate on the joined head when its tree equals a joined branch head whose gate result is trusted for the same base (STACKSPEC §13.6 states the join can skip that run).
