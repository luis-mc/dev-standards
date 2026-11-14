---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
spec: docs/architecture/DELIVERYSPEC.md
change: minor
---
DL-73 carries the PR exception (D290 to D292): on repositories the owner owns, agents may open pull requests, mark them ready and edit their title and description. Issues, comments, reviews, email and messages stay drafts, and merging stays the owner's. claude-setup writes the three `gh pr` allow rules into the project settings.
