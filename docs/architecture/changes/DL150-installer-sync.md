---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL150: `delivery_ci_install.py update` runs `artifact_prune.py --sync-workflow` after it rewrites `artifact-prune.yml`, so the project's `artifact_prune.workflows` list is applied and does not revert.
