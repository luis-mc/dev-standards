---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The ts installer no longer writes package.yml and smoke.json for a project with no Dockerfile and no packaged-program setting. The package job skips with a notice while its build command is the placeholder.
