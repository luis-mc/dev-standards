---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
`ci_runs.py` writes `host` (pool and Windows runners) and `os` (GitHub-hosted, from the runner labels) in `where`, drops the raw hosted runner name, and picks the latest real step for runs in progress (not Set up job, Post Run or Complete job).
