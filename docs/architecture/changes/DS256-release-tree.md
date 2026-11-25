---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
spec: claude/plugins/docs/references/artifactspec.md
change: minor
---
DS256: the Full Progress release timeline is a tree. A PR carries its releases, dashed arrows show a release waiting on a release, and a table lists them. Releases take `--pr`, `--release-start` and `--release-waits-on`; a dependent release is never live before what it waits on (R5.55 to R5.58).
