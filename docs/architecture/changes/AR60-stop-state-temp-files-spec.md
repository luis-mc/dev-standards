---
spec: claude/plugins/artifacts/references/artifactspec.md
change: patch
---
R8.8: the stop state's temp file is removed when a write fails, stale ones are swept, and a write that cannot finish is skipped with a warning (AR60).
