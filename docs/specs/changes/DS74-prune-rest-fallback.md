---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
`artifact_prune.py` refuses to run only when `gh` is missing and neither `GH_TOKEN` nor `GITHUB_TOKEN` is set; with a token it uses its REST fallback, so the prune works on a runner without the GitHub CLI.
