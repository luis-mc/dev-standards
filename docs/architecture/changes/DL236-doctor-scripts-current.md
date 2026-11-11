---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL236: `update` no longer reports `merged` for a file that got nothing from the template; it keeps it with a `.new`. The doctor check `ci.scripts-current` no longer calls `package.yml` and `smoke.json` missing on a ts project with no packaged program.
