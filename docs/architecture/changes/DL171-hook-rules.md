---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
DL171: DL-42 applies per command segment and only to stop or kill programs, so a `$(docker ps ...)` lookup inside docker exec, logs, inspect or cp is allowed. DL-63 reads the registry from the record folder (`record_dir` in docs/docs.json, then .claude/artifacts.json, default docs/project). Q-2 ignores question marks in code spans, block quotes and quoted text, and a closing "no question for you" line.
