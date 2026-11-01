---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

The load guard keeps its cache in the user's `~/.claude/` folder instead of the shared temp directory, and writes it with `tempfile.mkstemp` and `os.replace` (security audit Finding 6).
