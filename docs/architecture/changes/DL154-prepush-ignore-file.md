---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL154: the pre-push secret scan now reads .gitleaksignore and .gitleaks.toml from the pushed commit, not from the working tree, so a branch that carries its own ignore entries is no longer blocked.
