---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: patch
---

DS193: `docs_work.py strip --apply` now commits the removal of `docs/work/` (only that path). It used to stage the deletions and exit 0 without committing. If git refuses the commit, it exits 1, names what is still staged and prints the command to finish.
