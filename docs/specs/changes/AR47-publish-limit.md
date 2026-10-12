---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
Full Progress needs a publish only when what the owner sees changes (R9.6); a publish refused for claude.ai's daily limit is deferred until the reset with `mark-deferred`, and the end-of-turn hook stops blocking until then (R9.7); a task that ships nothing can say so with `--no-release REASON` and be Running without a release (R5.47a).
