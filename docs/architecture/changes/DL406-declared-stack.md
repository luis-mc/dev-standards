---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

The delivery plugin reads an optional `stack` block in `.delivery/config.json` and `delivery_doctor.py` fails at once (check `stack.tools`) for a detected tool that is neither known nor declared.
