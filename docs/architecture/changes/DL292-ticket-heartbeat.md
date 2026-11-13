---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL292: a gate refreshes its queue ticket (`beat_ts`) on every poll. `queue_list` drops a ticket from any host whose last beat is older than max(4 x poll_sec, 120 s) and logs it as `no heartbeat`. A dead gate on another host no longer blocks the queue for `slot_stale_min`.
