---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
One cloud launch now has one agent entry: the run id (cse_) is stored with the routine id (trig_), and every agent command takes either (DL96). DL-31 accepts "~HH:MM if <action> by HH:MM" and ignores past durations (DL97). SessionStart stops a watcher from an older plugin version by its pid and starts the newest (DL98). New check DL-93 refuses a cloud create that does not clear the account's connectors (DL100).
