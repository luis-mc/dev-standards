# DL396 report

## Files
- claude/plugins/delivery/scripts/delivery_watch.py: terminal-form check, NOT_READY_QUIET_MIN = 10, quiet-time hold
- claude/plugins/delivery/scripts/delivery_ledger.py: agent-check --reopen (agent.reopened event)
- claude/plugins/delivery/references/agent-brief-template.md: last-line rule
- docs/architecture/DELIVERYSPEC.md: DL-32a row
- tests: test_watch.py (3 new tests), test_dl396_reopen.py (new)
- docs/architecture/changes/DL396-not-ready-final.md, docs/features/delivery/changes/DL396.md

## Tests
`cd claude/plugins/delivery/tests && python3 -m unittest test_watch test_dl396_reopen test_dl392_agent_note_closed test_brief_template`: 101 tests, OK.

## docs_check
1 error: W1 on docs/work/DL396/REPORT.md (expected on a branch, this report). 1 warning: M1 on agent-brief-template.md (unmapped code, not from this change). T2 skipped (shallow clone).

## Branch head
Code commit 33775c3 (the report commit follows it).

READY
