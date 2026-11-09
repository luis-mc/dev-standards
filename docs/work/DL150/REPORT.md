# DL150 + DL157 report

## What changed
- `delivery_ci_install.py`: after `update` overwrites artifact-prune.yml it runs `artifact_prune.py --sync-workflow`. A failure prints the error and the fix and keeps the update (R13.72).
- `delivery_ci_install.py`: checks the `tz` of `.delivery/config.json`. On failure it runs `python -m pip install --user tzdata` (asks first when interactive), says what it did, and checks again (R13.73).
- claude-setup SKILL.md: a tzdata step.
- Spec R13.72 and R13.73, change notes, two new test files. No `.claude/suites.json` line was needed.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl150_install_sync test_dl157_tzdata test_dl112_install_imports test_dl120_install_keep_skip`: OK, 23 tests.
- `python3 claude/plugins/docs/scripts/docs_check.py`: one error, G1 `docs/architecture/decisions.md` is stale. It is a generated file I may not edit, and it is also stale on the base without my changes. The M1 error for the claude-setup change is cleared by the `Docs: none` line in the commit message.
- `gh workflow run spec-lint.yml --ref DL150-installer-sync-tzdata -f areas=delivery` (run 42717028523): all delivery jobs success (ledger/recorder/watcher/hooks, artifact pruning, train cleanup, CI scripts and templates, branch gate, setup preflight, packaged smoke, runner plan, change notes enforced, area mapping, delivery scripts); areas success. `docs check` failure (G1 above, same as base). Change notes and unrelated areas skipped.

## Branch head
See `git rev-parse origin/DL150-installer-sync-tzdata`; the report commit follows the code commit.

READY
