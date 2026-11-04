---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
agent_setup.sh reads engines.node from package.json and activates the lowest Node major that satisfies it (volta, fnm, nvm, else the official tarball with its SHA-256 checked). New guide for cloud routines (create disabled, update, then run; check list_runs after launch).
