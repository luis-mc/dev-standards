---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
artifact_prune.py stops paging when a `Link: next` URL is not https on api.github.com (or the GITHUB_API_URL host), so the token is never sent elsewhere. The interim-record converter reads build.py with a small AST check instead of `eval`.
