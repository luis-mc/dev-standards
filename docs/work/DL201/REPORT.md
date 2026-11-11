# DL201 report: install keep and report

Base check: fetched origin main (3c34540), branch reset onto it, `delivery_ci_install.py` exists.

## What changed
- `delivery_ci_install.py`: records sha256 of every file it writes in `.delivery/ci-install-state.json` (path -> hash, plugin version). New action `kept (project changes)`: on `update`, a plugin-owned file that differs from the record is kept, the new template goes to `<file>.new`, and the run prints `kept (project changes): <file>; new template in <file>.new; compare with: git diff --no-index <file> <file>.new` plus a delete-after-merge line. No record: a differing file counts as changed, and one line says the first update is careful. `ci-install.json` keep/skip still win. The prune-workflow sync records its own result so it is not seen as a project edit.
- `delivery_doctor.py`: `ci.scripts-current` warns and names each kept file.
- Tests: new `test_dl201_install_keep_and_report.py` (4 tests). Updated tests that pinned "overwritten" or overwrote an old copy: `test_dl120_install_keep_skip.py`, `test_ci_options.py`, `test_dl150_install_sync.py`, `test_dl172_setup_bounds.py`.
- Docs: R13.92 and R13.3 wording in `docs/features/delivery/spec.md`; feature note `docs/features/delivery/changes/DL201.md`; `docs/architecture/changes/DL201-install-keep-and-report.md`.

## Tests
- dl201 + dl120 + ci_options: 40 tests OK.
- Doctor tests (`test_*doctor*`): 61 OK.
- `tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only G1 and W1 (allowed).
- spec-lint.yml run 42995670470 (head 74990fb, areas=delivery,docs): all delivery jobs success (CI scripts, setup preflight, smoke, runner plan, artifact pruning, change notes, area mapping, branch gate, train cleanup, ledger/watcher), docs plugin success; `docs check` failed only with G1 and W1. An earlier run on the previous head failed the ledger job on test_dl172; fixed in the next commit.

## Follow-ups
- Windows and Linux hash CRLF as LF, so line endings do not count as edits.
- Nothing else touched outside the owned files, except the four existing tests listed above.

Branch head SHA: see `git rev-parse origin/DL201-install-keep-and-report` (report commit follows this text).

READY
