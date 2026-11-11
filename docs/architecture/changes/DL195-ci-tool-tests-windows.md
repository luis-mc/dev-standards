---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL195: the ci_tool tests skip the exec-bit check on Windows and use a cargo.cmd stand-in there, so they pass on Windows too.
