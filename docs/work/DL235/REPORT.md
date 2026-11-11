# DL235 report

Base check: ci_watch.py exists on origin/main.

## What changed
- ci_watch.py: default poll 60 s (minimum 30; under 1 s only for tests), backoff x1.5 up to 120 s while every run is queued, `gh api rate_limit` read each cycle (skipped for sub-second test intervals), sleep until reset when core.remaining < 200 (wait not counted in --timeout, never an error). Several SHAs and `--run ID` in one process; each commit reported as it completes; exit code is the highest.
- Rule DL-95 in agents-and-integration.md (project-setup rules asset) and a pre-tool check blocking `gh run watch` without `--interval` >= 60.
- Delivery spec R5.56, feature note, plugin change note.

## Tests
- `python3 -m unittest tests.test_dl235_ci_watch_quota`: 13 OK.
- Whole delivery tests dir: 1413 OK (1 skipped).
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed (after keeping sub-second intervals on the old fast path).
- docs_check: only W1 (this report under docs/work, expected).
- `spec-lint.yml areas=delivery`: run 1 (43079022340) failed on docs check, delivery CI scripts, delivery suite (caused by the sub-second interval clamp, fixed). Run 2 (43081403821): every job passed except `docs check`, whose local equivalent shows only W1.

## Follow-ups
- Rules file lives in project-setup, outside the owned list; the task pointed to it.
- Other specs (delivery-speed, models, project-setup) are covered by a `Docs: none` commit line.
Branch head: 164a8ad4775aebf64ebb5ea57a9ba3fc3f5de54f
READY
