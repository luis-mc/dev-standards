---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner-pool image runs `corepack enable` as root at build time. A job's own `corepack enable` as the unprivileged runner user no longer fails with EACCES.
