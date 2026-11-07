# DL101 report

## What changed
- delivery_runner_pool.py: `playwright_use` and `pick_browsers`. `plan` picks chromium when a served repo has a playwright.config.* (root, packages/*, apps/*) or lists @playwright/test / playwright. An explicit browsers choice wins. One line says why. The `--browsers` flag now defaults to auto.
- delivery_runner_pool.py doctor: `pool.<name>.browsers` fails on none + Playwright; `pool.<name>.browser-libs` runs a read-only `ldconfig` probe in the live image (fails if missing, warns if Docker is unreadable).
- delivery_ci_setup.py: passes the checkout to `plan`. delivery_doctor.py: passes the checkout to the pool checks.
- Notes: docs/architecture/changes/DL101-pool-browsers.md, docs/features/delivery/changes/DL101.md. The feature spec text is not edited (not in the owned files).

## Tests (from claude/plugins/delivery/tests)
- python3 -m unittest test_dl101_pool_browsers: 16 OK
- test_dl92_pool_fixes: 23 OK; test_runner_pool: 149 OK; test_doctor: 19 OK; test_ci_setup: 29 OK; test_e2e_chromium: 7 OK
- docs_check.py: G1 (stale decisions, expected) and T2 on test-cost spec (not mine). No W1.
- `gh workflow run spec-lint.yml --ref DL101-pool-browsers -f areas=delivery` (run 42322348822), watched with ci_watch.py: the delivery job (branch gate) passed. The `docs check` job failed at the DOCSPEC step. Locally the only error is G1 (stale decisions.md, expected on a branch). I did not confirm that G1 is the CI cause.

## Branch head
Code head b3853281fd12a88b625aa7e78fe4d3b287a40043 (this report is committed after it).

NOT READY
