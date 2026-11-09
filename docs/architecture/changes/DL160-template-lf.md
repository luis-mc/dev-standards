---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
DL160: the tech-stack template's .gitattributes now sets `* text=auto eol=lf`, so every text file checks out with LF on Windows too and a Windows worktree matches CI (prettier --check, hashes, diffs).
