# DL230 report

Base check: origin/main ci.yml had `playwright install --with-deps chromium`. OK.

## What changed
- `templates/ts/.github/workflows/ci.yml` and `nightly-full.yml`: one step with a shell `if` on `RUNNER_ENVIRONMENT`. `github-hosted` keeps `--with-deps`. Otherwise it prints that the libraries come from the pool's `POOL_BROWSERS=chromium` layer and runs `playwright install chromium` (no sudo).
- New `claude/plugins/delivery/tests/test_dl230_playwright_pool_deps.py` (2 tests).
- Delivery spec: one paragraph beside the E2E Chromium text. Feature note `docs/features/delivery/changes/DL230.md`. Change note `docs/architecture/changes/DL230-playwright-pool-deps.md`.

## Tests
- `python3 claude/plugins/delivery/tests/test_dl230_playwright_pool_deps.py`: 2 passed.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- Other tests pinning with-deps: only test_runner_pool.py (own fixture text, unaffected).
- `docs_check.py`: only W1 (this report, expected).
- spec-lint run 43070018836 (areas=delivery): all delivery jobs success (CI scripts and workflow templates, area mapping, branch gate and trust rule, setup preflight, runner plan, artifact pruning, ledger/recorder/watcher/hooks, train cleanup, packaged-program smoke, change notes, scripts/CI templates/cleanup). Other area jobs skipped. `docs check` failed on W1 only.

## Follow-ups
None. Strip docs/work before the join.

READY
