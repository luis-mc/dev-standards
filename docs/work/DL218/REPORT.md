# DL218 report

Base check: `delivery_ci_install.py` mentions `ci-install-base` (3 hits). Branch cut from origin/main.

## What changed
- `claude/plugins/delivery/scripts/delivery_ci_install.py`: `uses_prettier()` and `prettierignore()`. With Prettier detected (rc file, `prettier.config.*`, `prettier` key, or dependency), a marked block in `.prettierignore` lists `.delivery/ci-install-base/` and each managed `*.example.json` (not skipped ones). Other lines and the file's line endings are kept. A rerun is a no-op. `--dry-run` prints "would be written/updated" and writes nothing. No Prettier: no file.
- `claude/plugins/delivery/tests/test_dl218_install_prettierignore.py`: 9 tests.
- Spec R13.92 extended; feature note `docs/features/delivery/changes/DL218.md`; change note `docs/architecture/changes/DL218-install-prettierignore.md`.

## Tests
- `python3 -m unittest test_dl218_install_prettierignore` (in tests/): 9 OK.
- Existing installer tests (dl112, dl120, dl150, dl191, dl201, dl204): all OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only W1 (docs/work on branch, allowed).
- `spec-lint.yml` run 43048556981 (areas=delivery): success for area detection, train cleanup, area mapping, CI scripts and templates, setup preflight, packaged-program smoke, change notes enforced, artifact pruning, runner plan, branch gate and trust rule, plugin ledger/recorder/watcher/hooks, and the delivery roll-up. `docs check` failed on W1 only.

## Follow-ups
- Strip docs/work before the join (W1).

Head SHA: see the branch head after this commit.

READY
