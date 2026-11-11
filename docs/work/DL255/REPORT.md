# DL255 report

Base check: delivery_ci_install.py mentions artifact-prune and the 3-way merge (DL201): ok.

## What changed
- `delivery_ci_install.py`: one list rule for the prune workflow's `workflows:` line (`plan_prune_list`, `prune_rule`, `prune_set`). Project list wins; names the template added since the stored base are appended once; names the project removed stay removed. It covers every path that could replace the list: overwrite (file unchanged since the record, so the template used to win), merge, and conflict on the list line (the line is set aside, the rest takes the normal 3-way result). Prints `artifact-prune list: kept N project name(s)` and the added names.
- `artifact_prune.py` needed no change.
- New tests: `tests/test_dl255_prune_list_merge.py` (6 tests).
- Docs: delivery spec R13.72, feature note, architecture change note.

## Tests
- `python3 tests/test_dl255_prune_list_merge.py`: 6 ok.
- dl150, dl201, dl213, dl218, dl227, dl236, dl242, dl245 install/prune tests: all ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only the expected W1 on docs/work/.
- spec-lint dispatch (areas=delivery), run 43111897082: every delivery job success; only `docs check` failed, on W1.

## Follow-ups
- Without a stored base a project's file is kept as `.new` (DL201), so template additions are not appended in that case.

Branch head SHA: 7c01f70b33672bda43f68c39c7f1557a5baa5b46 (code and docs; this report is committed after it)

READY
