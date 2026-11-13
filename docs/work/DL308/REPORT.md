# DL308 report

Base check: the installer (`delivery_ci_install.py`) keeps a base per file in `.delivery/ci-install-base/`, so the install step exists.

## What changed
- `claude/plugins/delivery/scripts/template_adopt.py` (new): `status`, `diff PATH`, `adopt PATH|--all [--dry-run] [--write-conflicts]`. Reuses the installer's track, skip and base-path logic. Three-way merge with `git merge-file -p`. A missing base is recorded as the current template.
- `delivery_ci_setup.py`: one docstring line listing the commands (registration only).
- `tests/test_dl308_template_adopt.py` (new, 15 tests).
- Spec: new R13.96 in `docs/features/delivery/spec.md`. Change note `docs/architecture/changes/DL308-template-adopt.md`.
- docs_check named no M1, so no feature note was needed.

## Tests
- `python3 -m unittest test_dl308_template_adopt` (in tests/): 15 ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- install tests (`test_dl2*install*`): 39 ok.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only the expected W1 on docs/work/.
- spec-lint.yml, areas=delivery, run 43447942386: every delivery job passed; only `docs check` failed on the expected W1 (plus T2 warnings on other specs).

## Follow-ups
- `adopt --all` skips files with no base (run `status` first to record one).
- The installer's state hash is not updated by adopt; the next `update` treats an adopted merge as a project change and merges again, which is safe.

Branch head SHA: see the last commit on DL308-template-adopt.

READY
