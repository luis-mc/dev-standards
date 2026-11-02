---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
tech-stack-setup no longer carries the CI and delivery templates. It copies hooks, linters and guards, and calls the luismc-delivery installer at the end of step 1. It asks the owner for the CI option per OS.
