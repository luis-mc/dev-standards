# DL250 report

Base check: `cmd_edit_content` with `shutil.rmtree(str(d))` was present on origin/main. OK.

## What changed
- `project_artifacts.py`: new helper `replace_content_dir` (stage in `.<key>.new-<pid>`, rename old to `.<key>.old-<pid>`, rename stage in, then remove old; removal failure is a warning). A locked folder falls back to in-place replace, or stops with "content/<key> is in use ...; nothing changed". Invalid content restores the old folder before the error, so "nothing written" is true. `retire` sets the folder aside first and stops with nothing changed if locked. Dot-folders are skipped by the content-folder check; leftovers are cleaned on the next run.
- New tests: `claude/plugins/docs/tests/test_dl250_edit_content_safe.py` (5 cases).
- Docs: artifacts spec row, feature note `docs/features/artifacts/changes/DL250.md`, change note `docs/architecture/changes/DL250-edit-content-safe-replace.md`.

## Tests
- `python3 -m unittest tests.test_dl250_edit_content_safe` (in claude/plugins/docs): 5 OK.
- `unittest discover tests -p "test_dl2*.py"`: 36 OK.
- `run_suite.py project-artifacts` cases test_edit_content (3), test_retire (7), test_decisions_edit_content (1): all pass.
- `docs_check.py` locally: only W1 (this report under docs/work/, allowed by the brief).
- spec-lint dispatch run 43104578921 (areas=artifacts): "artifact renderer, commands and hooks" success. "docs check" fails, only on the W1 report file (same as local). First run 43101613679 was cancelled (outage) and its re-run failed on the same docs check; "docs plugin" job succeeded there.

## Follow-ups
- Strip docs/work before the join (docs_work.py strip).
- features/docs spec maps the script; covered by a `Docs: none` line in the commit.

READY
