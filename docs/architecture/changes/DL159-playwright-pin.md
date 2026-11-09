---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL159: the runner pool's pinned Playwright fallback moves from 1.62.1 to 1.65.0 (npm latest) in delivery_runner_pool.py, the pool Dockerfile and compose.yaml. It is used only when no lockfile or pool .env sets a version.
