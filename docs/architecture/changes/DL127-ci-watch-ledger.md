---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

DL127: `delivery_ledger.py agent-check` records `last_checked`, `cleanup.py --pr N` closes the agents of the shipped train's cargo, and `show` names open agents whose task the project record shows as Live, Dropped or Built. DL132: `ci_watch.py` writes the ledger of the main checkout, found from the git common dir, even when run in a worktree. DL138: `ci_watch.py` matches the train by branch or PR head, creates it when none exists, prints the plan command when no branch is found, and `plan --branch` returns the open train of that branch instead of a duplicate. DL139: `ci_watch.py` watches every workflow run for the head commit and fails when any fails; `--only-workflow` keeps the old single-workflow watch.
