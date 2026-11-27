---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
task: DS303
---
The hooks refuse a session's `gh pr merge` in both merge modes (the watcher merges); in manual mode Q-4 and the Stop hook never ask a session to merge, and the Stop hook says one warning line once. The Stop hook drops the past-due Expected check (the docs plugin keeps it). Rule keys fixed: DL-124, DL-39, DL-35. The clarifying-questions rule drops the safety-limits line.
