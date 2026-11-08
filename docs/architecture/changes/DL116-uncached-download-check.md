---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL116 adds DL-94: a workflow step that downloads a pinned tool must go through the per-runner cache with a sha256 check. The new `workflow_fetch_check.py` finds the bad steps, and the pre-tool hook refuses a write to `.github/workflows/` that adds one.
