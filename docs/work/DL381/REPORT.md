# DL381 report

Files:
- claude/plugins/delivery/scripts/delivery_watch.py (cancel_superseded, two helpers)
- claude/plugins/delivery/tests/test_dl381_cancel_superseded.py (new, 6 tests)
- claude/plugins/delivery/tests/test_watch.py (existing cancel test gets the commit and jobs routes)
- docs/features/delivery-speed/spec.md (R5.24 and test row), docs/features/delivery-speed/changes/DL381.md
- docs/architecture/changes/DL381-cancel-superseded-safe.md (plugin note, minor)

Tests:
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl381_cancel_superseded test_watch test_dl298_head_runs test_dl109_watcher_no_windows test_dl118_rearm_unstoppable test_dl96_watcher_rearm test_watch_ci_runs`: 132 tests OK
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings (M1 for features/delivery cleared by a `Docs: none` line in the commit)

Branch head: see `git rev-parse origin/DL381-cancel-superseded-safe` (the commit that adds this report).

READY
