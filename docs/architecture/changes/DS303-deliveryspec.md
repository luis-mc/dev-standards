---
spec: claude/plugins/delivery/references/deliveryspec.md
change: minor
task: DS303
---
The watcher is the only merger: DL-03 says who merges per `watcher.merge_mode`, and a session's `gh pr merge` is denied in both modes; DL-08 says a task agent opens drafts only and the orchestrator or the watcher opens the ready PR; DL-73 cites both. The fold runs on the default branch after the merge (DL-10, DL-24). DL-12 is the one agent test rule; DL-30 matches the measured check, DL-31 applies in chat, DL-74 is conditional on `no_attribution`. Q-1 to Q-5 are rows of section 1; DL-04, DL-34, DL-61, DL-62, DL-63 and DL-70 to DL-72 are retired as merged; DL-132 names the task branch. The Today column and the counts line match the hooks (`tools/test_rule_ids.py`).
