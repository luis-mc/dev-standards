---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
spec: docs/specs/delivery/DELIVERYSPEC.md
change: minor
---
The Stop hook can no longer trap a session on DL-14 or DL-18: `delivery_ledger.py` gains `smoke --pr N` and `cleaned --pr N`, which verify the production smoke run and the removal of the train's branches and worktrees with `gh` and git and record them on every row with that pr; the DL-14 and DL-18 messages name the project's configured command and then the recording command; and the new `stop_repeat_limit` (default 3, 0 = never) stops blocking a finding that blocked that many turn ends with no change to the ledger fields it depends on, announcing it once per session instead.
