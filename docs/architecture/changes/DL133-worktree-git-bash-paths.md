---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The DL-53 worktree check now turns Git Bash paths (/c/Work/x) and WSL paths (/mnt/c/Work/x) into the Windows form (C:/Work/x) and compares without case, so a worktree under the work root is no longer refused. A real path outside the work root is still refused.
