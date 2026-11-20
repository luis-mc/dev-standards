# DL375 report: rerun narrowing

Files:
- claude/plugins/delivery/templates/shared/scripts/delivery/rerun_tests.py (new: parsers for pytest/unittest, vitest/jest, Playwright, go, cargo, nextest; argument builders; `decide`; CLI)
- claude/plugins/delivery/templates/shared/scripts/delivery/CONTRACT.md (rerun_tests.py entry)
- claude/plugins/delivery/tests/test_dl375_rerun_narrowing.py and tests/fixtures/dl375/ (seven recorded fixtures)
- docs/features/delivery-speed/spec.md (R5.18 and its test row), docs/features/delivery-speed/changes/DL375.md, docs/architecture/changes/DL375-rerun-narrowing.md
- ci_rerun_first.py, rerun_args.py, ci_scope.py: unchanged, reused (ci_scope.decide, area_select.select). tools.json: unchanged; it holds tool pins, not a script list.

Tests:
- `python3 -m unittest test_dl375_rerun_narrowing` (in claude/plugins/delivery/tests): 33 tests OK.
- Existing: test_dl181_ci_rerun_first, test_dl183_rerun_first_pending, test_dl294_rust_release_scope, test_dl295_rust_scope: all 96 OK together with the new file.
- `tools/ci_areas.py --branch-advice`: heavy delivery area, spec-lint workflow; not started (no Actions per brief).

docs_check: 2 errors, both expected or not mine.
- W1: docs/work/DL375/REPORT.md is on the branch by design; strip before any join.
- G1: docs/architecture/decisions.md is stale; generated file, no decisions table touched here.

Not wired: no CI workflow template calls rerun_tests.py yet; it is the helper and its contract.
Branch head SHA: see the last commit on DL375-rerun-narrowing (git rev-parse).

READY
