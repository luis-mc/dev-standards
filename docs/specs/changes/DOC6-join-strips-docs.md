---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
The generated join.py strips docs/work/ with the luismc-docs docs_work.py when that plugin is present (DOCSPEC R10.3), commits the removal, and records each report summary in join-result.json and .delivery/docs-summaries.md for the ready pull request body; it skips cleanly when the plugin is absent.
