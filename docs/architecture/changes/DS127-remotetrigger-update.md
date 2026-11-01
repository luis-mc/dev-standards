---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The pre-tool hook now treats only RemoteTrigger create and run as launches, so update (for example disabling a finished routine), list, get, list_runs and get_run_log are no longer refused for a missing model or counted against the cloud cap.
