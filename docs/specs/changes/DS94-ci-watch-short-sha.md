---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
`ci_watch.py` resolves an abbreviated commit sha to the full one (git, then the GitHub API) before listing runs, since `gh run list --commit` matches full shas only; an unresolvable one exits 2 instead of waiting until the timeout.
