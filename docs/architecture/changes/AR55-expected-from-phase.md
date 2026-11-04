---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
spec: claude/plugins/artifacts/references/artifactspec.md
change: patch
---
`set-task-status` and `task-add --release` no longer refuse a release when only `--phase`, `--basis` or a status is given: Expected follows the end of the last phase (the date rolls past midnight). An explicit `--expected` that contradicts the phases is still refused, and the message names the right value.
