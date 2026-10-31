---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: patch
---
runner_plan.py runners re-runs a CI run only when it is on the branch's current head, is the newest run of its workflow for that head, nothing of the branch is running and it did not end cancelled (config key rerun_cancelled); every re-run and skip is a ledger event and a report.log line, and the ledger module is found in the installed plugin cache so the events reach the ledger.
