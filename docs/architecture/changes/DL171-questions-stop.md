---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
DL171: the shipped questions_stop.py no longer detects a question asked in plain text (Q-2 lives only in the delivery Stop hook). It keeps parking questions while agents run (Q-1, Q-5).
