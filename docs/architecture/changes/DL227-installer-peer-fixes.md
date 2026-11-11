---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The installer never copies .pyc files and keeps a .gitignore block for them. The prune workflow sync accepts indent and CRLF, and a failed sync is not reported as merged. Ignored files are not listed under "not in git yet".
