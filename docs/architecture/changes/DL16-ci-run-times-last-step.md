---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The ts CI template writes the run times as the last step of its last job (`e2e`) instead of a job of its own, so no extra job waits for a runner; the artifact name `ci-run-times` is unchanged.
