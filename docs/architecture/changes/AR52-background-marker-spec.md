---
spec: claude/plugins/artifacts/references/artifactspec.md
change: patch
---
R8.8 and R8.10: watch-only background commands do not arm the end-of-turn check, the check fires once per marker, and the marker is removed when a task is active or once the turn was let through after it was told.
