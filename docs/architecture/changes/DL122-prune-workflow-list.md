---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL122: the list of workflows that artifact-prune.yml reacts to is now owned by the project. It is the `artifact_prune.workflows` list in `.delivery/config.json`, and it defaults to `CI` and `Package`. `artifact_prune.py --sync-workflow` writes the list into the workflow file, `--check-workflow` reports a difference, and `--print-workflows` prints it. A project that sets nothing sees no change.
