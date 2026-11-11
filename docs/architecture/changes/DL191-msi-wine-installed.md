---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

windows-msi-check.yml installs Wine and xvfb only when they are missing, so the job runs on a pool runner, which has no sudo.
