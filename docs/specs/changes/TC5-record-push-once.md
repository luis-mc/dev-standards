---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---

Writing commands commit the record but no longer push it; the record is pushed once, at the end of the turn, by `pending`, by a new `push` command and by a new before-command hook ahead of `gh pr create`, `gh pr ready` and `gh pr merge` (R4.28, R4.29, R7.6, R8.16, R8.17). This stops one secret-scan run per record commit.
