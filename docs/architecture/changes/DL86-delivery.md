---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The runner pool image now installs the GitHub CLI (gh) from a pinned release tarball checked by SHA-256, as hosted runners do. Workflows that run `gh api` or `gh pr` no longer fail with "gh: command not found". The pool-check workflow tests for gh and prints its version.
