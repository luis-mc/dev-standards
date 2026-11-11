---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
ci_watch.py polls every 60 s, backs off while runs are queued, waits out a low GitHub quota, and watches several commits or runs in one process. Rule DL-95 and a pre-tool check block `gh run watch` without `--interval 60` or more.
