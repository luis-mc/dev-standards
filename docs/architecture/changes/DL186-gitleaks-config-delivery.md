---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The installer writes .gitleaks.toml when the project has none; the shared copy moved here and its project-named-secret and project-database-url rules skip type annotations, fields and empty values.
