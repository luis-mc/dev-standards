---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The Windows runner files step takes back and resets files already in the runner folder before it locks it, so files a previous account made (the `_work` tool cache) stay readable after an account switch (DL356).
