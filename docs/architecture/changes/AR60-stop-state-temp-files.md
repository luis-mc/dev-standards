---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
The hooks' state write removes its temp file when it fails, retries a moment when Windows holds the file, sweeps temp files over 60 seconds old, and warns instead of failing the hook (AR60).
