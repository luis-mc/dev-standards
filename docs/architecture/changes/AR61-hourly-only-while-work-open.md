---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
The end-of-turn hook and `publish_hourly.py` ask for the hourly Full Progress publish only while a task is Running, Waiting or Needs you (AR61, decision D20).
