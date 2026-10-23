---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
The ready-PR guard (`session_guard.py`) looks up `gh pr ready N -R OWNER/REPO` in the repository named, so it judges that pull request's head branch instead of the same-numbered pull request of the current repository.
