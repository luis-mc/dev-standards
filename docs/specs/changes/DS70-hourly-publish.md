---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
Full Progress is published at least hourly and whenever a release task's status or phase changes: the end-of-turn hook blocks on both (R8.18, R9.8, R9.9), `pending --refresh` and `publish_hourly.py` drive the hourly publish (R9.10), `pending` records the publish copy's hash and write time and `mark-published` refuses a stale or edited copy (R9.11), and `check` and the hook flag open rows whose Expected time has passed (R6.14, R8.19).
