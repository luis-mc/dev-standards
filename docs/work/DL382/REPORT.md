# DL382 report

## Files
- claude/plugins/delivery/scripts/delivery_ledger.py: branch guard, autoclose, close, close-stale, show runs autoclose, `closed` counts as finished
- claude/plugins/delivery/scripts/hook_stop.py: grouped DL-03/14/18 lines, PR-less close hint, autoclose before the checks
- claude/plugins/delivery/tests/test_dl382_ledger_stale.py (new, 14 tests)
- docs/features/delivery-speed/spec.md (R5.25 and test row), docs/features/delivery-speed/changes/DL382.md, docs/architecture/changes/DL382-ledger-stale-trains.md

## Tests
- `python3 -m unittest discover -s tests -p "test_dl382*.py"` (in claude/plugins/delivery): 14 tests OK
- unittest of test_ledger, test_recording, test_stop, test_watch, test_dl96_*, test_dl127, test_dl133, test_dl156, test_dl163, test_dl171, test_ledger_root_worktree, test_watch_ci_runs: 251 tests OK
- Full plugin suite not run (too slow; only what I touch).

## docs_check
2 errors, none from this branch's content: G1 (docs/llms.txt stale) also fails on clean origin/main; the release regenerates it. W1 is expected (this report lives in docs/work/ on the branch only).

## Notes
- Auto-close skips trains that already have merged_at, so DL-14/DL-18 still fire for normally merged PRs. A PR-less train with merged_at is moved into the close hint.
- branch-gone needs a train older than 24 h, so an unpushed new train is not closed.
- hooklib.TERMINAL_TRAIN is not mine to edit; hook_stop adds `closed` locally. Other hooks that read TERMINAL_TRAIN may still see a closed train; DL-02 and DL-03 read state, which excludes it.

Branch head: committed code at 97bd535 (the report commit follows it).

READY
