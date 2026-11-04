---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
spec: claude/plugins/docs/references/docspec.md
change: patch
---

An old design system version may now move to `docs/archive/design-system-vN/` (or `docs/archive/design-system/vN/`). The DS3 check and the layout guard no longer call the missing number a gap when its folder is in the archive. The freeze guard treats a delete of a numbered folder as an archive when the folder is in `docs/archive/`. A missing number with no archived copy still warns. R15.1 says so in one sentence.
