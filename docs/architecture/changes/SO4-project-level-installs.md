---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
claude-setup now defaults to project level. It installs plugins with `--scope project`, turns on transcript-folds in the project, and adds `extraKnownMarketplaces` to the project settings when it is missing.
