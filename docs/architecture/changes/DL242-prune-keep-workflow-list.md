---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

# DL242: prune sync keeps the workflow list

`artifact_prune.py --sync-workflow` no longer replaces a project's workflow list with the default when the config has no `artifact_prune.workflows`. It keeps the file's list, writes the default only for a new file or a file with no list, and prints the source (config, existing file, default).
