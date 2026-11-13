---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL307: `fast_guards.py` runs the `always_on_guards` declared in `gate.json` whose input globs match a changed file. The ts template declares the boundary check this way.
