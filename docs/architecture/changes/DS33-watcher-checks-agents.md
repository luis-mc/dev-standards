---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The background watcher checks every running agent row every 15 minutes (cloud rows by PR, commits and workflow runs; local rows by log time and branch head), records last_checked, last_activity, head_sha, branch, check_note and a stalled flag, never marks an agent done by guess, and the ledger write retries on Windows access denied (WinError 5); a watcher-recorded check counts for DL-32.
