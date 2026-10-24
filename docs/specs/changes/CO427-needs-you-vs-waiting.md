---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---
The At a glance group "Waiting or on hold" is now "Waiting for other work", and a Waiting or On hold task that waits on the owner moves to Needs you, set with the new optional `waits_on` field (`--waits-on owner|work` on `task-add` and `set-task-status`, default `work`, R5.34a); the rows of both groups read what they wait on first, then the item, then Expected, and the Needs you count, sentence and feature summary include the owner's waits.
