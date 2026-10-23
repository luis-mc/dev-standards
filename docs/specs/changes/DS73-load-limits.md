---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/specs/delivery/DELIVERYSPEC.md
change: minor
---
Machine load guard (DL-77, DL-78, DL-79): luismc-delivery holds new heavy work, local agents and workflows while memory is above 85% or CPU above 60% (limits per machine and per project), notices it at Stop and SessionStart, and ships a runner gate hook with a doctor check.
