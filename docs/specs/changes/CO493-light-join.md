---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
spec: claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md
change: minor
---
A release join is light: `join.py` merges, resolves conflicts, then runs typecheck and lint of the touched packages and the fast guards (`gate.json`: `"join"` on a step, `join_guards`), never the tests or a branch gate on the joined head; the ready PR's CI is the one full run, with no sandbox gate awaited and no re-gate after a join fix (DL-11, DL-13, §13.6). The agents-and-integration rule says so.
