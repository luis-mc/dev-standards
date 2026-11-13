---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The pool setup takes `--only windows|linux`, sets CI_RUNS_ON_WINDOWS for Windows repositories, removes a leftover non-generic runner label only with a yes, grants ci-* accounts the symbolic-link right and registers the host-load task with PowerShell cmdlets (DL316, DL319, DL320).
