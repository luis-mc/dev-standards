---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
task: DS305
---
STACKSPEC and AUTHSPEC move to the plugin's `references/`; `check_stack.py`, `preflight.py` and `ci_pin.py` move to its `scripts/`. claude-setup writes `clarifying-questions.md` only for a user-level setup and removes an unchanged project copy; the agents rule file is shorter; the plugin tests run under `unittest discover`.
