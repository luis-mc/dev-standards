---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The design edit hook (`hook_design_edit.py`) no longer returns `permissionDecision: allow` on the first breach in a turn. It passes the warning as `additionalContext` only, so the normal permission rules apply. It also judges what an edit adds: a check fires only when its matches increase from the old text to the new text, a new stylesheet is a breach but an Edit to an existing one is not, and test files are skipped.
