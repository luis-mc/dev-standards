---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL112: a failed import of a sibling module in ci_watch.py or fallback_launch.py now prints one line naming the missing file, its folder and the fix, and exits 2. The installer checks the imports of every script it manages under scripts/delivery/ after install or update (and with --dry-run), lists missing modules, lists managed files not tracked by git, and exits 3 when an import is missing.
