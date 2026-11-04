---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Delivery hooks: a block (exit 2) now survives the python fallback in `hooks.json`, which runs `python` only when `python3` is missing. The post-tool recorder reads PowerShell calls, resolves `git push origin HEAD` to the current branch, and ignores branch deletes. A heavy call is no longer dropped when its hook shell exits. The Stop hook reads Expected in the owner zone, accepts `~HH:MM`, picks the nearest year for a date with no year, and checks stalled and pushed agents.
