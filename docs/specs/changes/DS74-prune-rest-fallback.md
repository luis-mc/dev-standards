---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
`artifact_prune.py` gains the REST fallback (GH_TOKEN or GITHUB_TOKEN) for a runner without `gh` and refuses to run only when `gh` is missing and neither token is set, so the build-artifact prune works on a runner without the GitHub CLI.
