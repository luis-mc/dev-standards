---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
Every `runs-on` in the workflow templates reads the per-job variable `CRSP_<JOB>` first, then the old chain unchanged. The doctor lists the per-job overrides it finds set.
