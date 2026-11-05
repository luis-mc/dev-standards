---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Four fixes from a guided pool run. `pool_agents.py` saves `agents.json` in place when the file is a bind mount (EBUSY or EXDEV on replace). A rerun keeps a Windows runner that equals the planned one and removes only runners that differ. Labels are compared without regard to case in the plan, verify and the doctor. The Windows hook scripts are copied to `<machine folder>/runner-hooks` with the full python path in the wrappers (D99).
