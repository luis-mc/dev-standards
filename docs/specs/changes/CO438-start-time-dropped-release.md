---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
`set-task-status ID STATUS --started "DD Mon ~HH:MM"|HH:MM` sets when a task began, so the bar of a waiting or needs-you no-release task on the timeline starts there and not at "now"; a task that first moves to Running gets it automatically (R5.48). A ninth status, `Dropped`, closes a task folded into another or no longer wanted without claiming it shipped: not open, off the timeline, listed under `Live or built` as `dropped: folded into RELEASE-n`, with `--into ID` (required for a release) or `--reason TEXT` (R5.49, R6.1).
