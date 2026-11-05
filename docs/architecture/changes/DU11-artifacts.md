---
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: patch
---
The plan-rows check (`plan_rows_check.py`) now counts a numbered row only when it sits under a Markdown heading whose text starts with Plan, Proposed, Proposals or Findings. Any other heading ends that section and a "Not proposed" heading never counts, so a status list of finished items no longer blocks the end of the turn. The Stop hook message and the `task-add` skill state the heading rule.
