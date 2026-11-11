# DL229 report

Base check: `delivery_ci_install.py` mentions `package.yml`: yes (branched from origin/main).

## What changed
- `delivery_ci_install.py`: on the ts track, `package.yml` and `smoke.json` are skipped when there is no Dockerfile (root, or `packaged_program.dockerfile`) and no `packaged_program` setting (string, or object with `build`) in `.delivery/config.json`. The run prints `skipped: no Dockerfile and no packaged-program setting (<path>)`; the summary counts them as skipped. An installed file is never deleted; it is listed with the same hint.
- ts `package.yml` template: build command in job env `PACKAGE_BUILD`; a guard step prints a notice and skips the other steps (job succeeds) while it is the placeholder and no Dockerfile exists.
- Tests: `tests/test_dl229_no_package_placeholder.py` (6 tests).
- Docs: spec R13.94, feature note `docs/features/delivery/changes/DL229.md`, change note `docs/architecture/changes/DL229-no-package-placeholder.md`.

## Tests
- `python3 -m unittest test_dl229_no_package_placeholder`: 6 OK.
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p 'test_*install*'`: 53 OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py` (local): only W1 (this report), expected.
- spec-lint run 43070265426, areas=delivery: all delivery jobs success (setup preflight, artifact pruning, ledger/watcher/hooks, change notes, branch gate, area mapping, runner plan, CI scripts and templates, packaged-program smoke test, train cleanup, and "delivery scripts, CI templates, cleanup, prune, change notes"). "which areas" success. "docs check" failed only on W1 (this report). Other jobs skipped.

## Follow-ups
- Only the ts track has the docker placeholder; go, rust and dotnet are unchanged.
- Remove this report with `docs_work.py strip` before the join.

READY
