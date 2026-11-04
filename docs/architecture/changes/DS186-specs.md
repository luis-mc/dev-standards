---
plugin: claude/plugins/specs/.claude-plugin/plugin.json
change: patch
---

spec_check.py now runs from any directory: it finds its default STACKSPEC and AUTHSPEC next to the script and skips a default that is missing. It also exits 2 on a file that is not UTF-8, ignores a byte-order mark, resolves lettered outbound citations, carries a document name across `§9, §10`, ignores headings in fenced blocks and `<!--` in inline code, and accepts a directory. The skill commands use `${CLAUDE_PLUGIN_ROOT}`.
