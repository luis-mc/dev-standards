---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/specs/delivery/DELIVERYSPEC.md
change: minor
---
luismc-delivery delivers the clarifying-questions rules (Q-1..Q-5) in the SessionStart context every session and enforces Q-5: PreToolUse denies a second AskUserQuestion batch while the session's agents still run; the recorder now keeps the owner's latest prompt and each agent's launching session.
