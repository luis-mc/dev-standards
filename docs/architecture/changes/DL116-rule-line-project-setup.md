---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
The claude-setup rules gain the DL-94 line: CI jobs fetch pinned tools through scripts/delivery/ci_tool.py, a per-runner cache with a sha256 check and retries, never a bare download into RUNNER_TEMP (DL116).
