# DL336 report

Fix: `ci_watch.head_of` read `origin/HEAD` as a branch named `origin`. It now uses full ref names, drops `*/HEAD` and the default branch.

## Files
- claude/plugins/delivery/templates/shared/scripts/delivery/ci_watch.py
- claude/plugins/delivery/tests/test_dl336_ci_watch_default_head.py
- docs/features/delivery/spec.md (R5.62 and test row)
- docs/features/delivery/changes/DL336.md
- docs/architecture/changes/DL336-ci-watch-default-head.md

## Tests
- `python -m unittest test_dl336_ci_watch_default_head test_dl265_merge_link_hint test_dl127_ci_watch_ledger test_ci_options` (in claude/plugins/delivery/tests): 49 tests, OK.

## docs_check
- G1 `decisions.md` stale: generated file, not touched, not from this branch.
- M1 `delivery-speed/spec.md` maps ci_watch.py: answered by `Docs: none` in the commit message; behaviour is in the delivery spec (R5.62).

## Head
See the last commit on branch DL336-ci-watch-default-head.

READY
