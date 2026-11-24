# DL410 report: Cypress rerun adapter

Files:
- claude/plugins/delivery/templates/shared/scripts/delivery/rerun_tests.py (runner `cypress`, log and JUnit parsers, `--spec a,b`, test globs, docstring)
- claude/plugins/delivery/tests/test_dl410_rerun_cypress.py (7 tests)
- docs/features/delivery/spec.md (R5.68 after R5.66; R5.67 is free for DL409)
- docs/architecture/changes/DL410-rerun-cypress.md, docs/features/delivery/changes/DL410.md, docs/features/delivery-speed/changes/DL410.md
- rerun_args.py: unchanged (needs no runner name).

JUnit XML: read (file attribute of each testsuite with a failed case).

Tests: `cd claude/plugins/delivery/tests && python3 -m unittest test_dl410_rerun_cypress test_dl375_rerun_narrowing test_dl181_ci_rerun_first test_dl183_rerun_first_pending` -> 74 tests OK.
ci_areas --branch-advice: "unreadable diff" (shallow clone); I did not start workflows.
docs_check: 0 errors, 0 warnings.
Branch head (code commit): dbef03aefe9b9df1089cd998cbf3295dcd2f14ca

READY
