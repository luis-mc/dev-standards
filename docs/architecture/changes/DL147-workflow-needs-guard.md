---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL147: a job whose `needs` include a skippable job now carries an `if:` that starts with `!cancelled()` and checks `needs.<name>.result`, so GitHub's implicit success() no longer skips it. The delivery workflow templates follow the rule, and `test_dl147_workflow_needs.py` enforces it for every template workflow.
