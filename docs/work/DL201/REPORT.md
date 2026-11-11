# DL201 report: install keep, merge and report (step 2 done)

## Step 2: 3-way merge (D206)
Base check: fetched the branch; the installer writes `.delivery/ci-install-state.json` and has `kept (project changes)`.

### What changed
- `delivery_ci_install.py`: stores each template as written in `.delivery/ci-install-base/<path>`. On `update`, a project-changed file with a base goes through `merge3` (difflib, line based, LF). Clean: written, action `merged`, base refreshed. Conflict: project file untouched, `<file>.new` holds markers (`<<<<<<< project` / `||||||| base` / `=======` / `>>>>>>> template`), action `conflict`, and the run prints `resolve <file>.new, then copy it over <file> and rerun update` with the count. No base: step-1 behaviour (kept, plain `.new`), then the new template is recorded as the base. CRLF files keep CRLF. A resolved or stale `.new` is removed when the file ends `same`, `merged` or overwritten. Summary line: `summary: N written, N overwritten, N merged, N conflict, N kept, N same, N skipped`. Exit 0 with conflicts.
- `delivery_doctor.py` (`ci.scripts-current`): also warns for a file with a pending `<file>.new`.
- Tests: 7 new cases in `test_dl201_install_keep_and_report.py` (clean merge, conflict, resolved rerun, no base, CRLF, unchanged overwrite, same change both sides). `test_dl120_install_keep_skip.py` and `test_ci_options.py` now drop the base first, since they test the no-base path.
- Docs: R13.92 and R13.3 in the delivery spec, the DL201 feature note, the architecture note. They recommend the project commits `.delivery/ci-install-base/` so every clone can merge.

### Tests
- dl201 + dl120 + ci_options + dl150 + dl172: 58 OK.
- Doctor tests (`test_*doctor*`): 61 OK.
- `tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only G1 and W1 (allowed).
- spec-lint.yml run 42996858216 (areas=delivery,docs): success: area detection, runner plan, setup preflight, branch gate and trust rule, artifact pruning, plugin ledger/recorder/watcher/hooks, CI scripts and workflow templates, packaged-program smoke test, docs plugin, change notes enforced and folded, area mapping, train cleanup, delivery summary job. Skipped (not in scope): change notes, change notes folded, specs/templates/AUTHSPEC, branch gate shards, model profiles, artifact renderer, transcript folds. Failure: `docs check` with G1 and W1 only.

### Follow-ups
- Deviation: after a clean merge the record holds the hash of the template, not of the merged file. With the merged file's hash, the next update would see the file as untouched and overwrite the project's lines silently. The cost: the doctor keeps naming a merged file as changed by the project, as it does for any edited file.
- On a conflict the old base is kept, so a rerun after the hand fix merges cleanly (both sides then hold the same change).
- Nothing outside the owned files changed, except `test_ci_options.py` and `test_dl120_install_keep_skip.py` (step 1's four tests).

Branch head SHA: see `git rev-parse origin/DL201-install-keep-and-report` (report commit follows this text).

## Step 1 (short)
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

READY
