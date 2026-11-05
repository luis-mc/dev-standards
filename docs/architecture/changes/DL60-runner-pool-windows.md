---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner pool setup now works on Windows with Docker Desktop and WSL2. It reads the runner SHA from the release notes marker, leaves one CPU of headroom in the WSL processors, writes every pool file with LF line endings, and gives each agent its own copy of the runner in `/agents/SLUG` so the runner can write beside `config.sh`.
