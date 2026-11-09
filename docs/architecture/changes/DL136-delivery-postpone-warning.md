---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

Rule DL-136: a routine held for an owner answer is paused, never postponed by minutes. The pre-tool hook warns (never blocks) when a RemoteTrigger create or update sets run_once_at less than 2 hours ahead while the ledger holds an unanswered owner question.
