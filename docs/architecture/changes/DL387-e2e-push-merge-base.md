---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---

e2e_push_check.py counts only the e2e specs the branch itself changes, measured from the merge base with origin/<default> as branch_gate.py does. A merge of the default branch no longer makes the push impossible to pass.
