# DL162 report

## What changed
- `delivery_runner_pool.py`: new `template_sources`, `pool_template_diffs`, `copy_pool_templates(dest, copy_from=None, only=None)`; `write_pool_files` uses it; `refresh_plan` returns `files`; `Executor.refresh` backs up the differing files to `bak-<UTC time>/`, copies the templates, builds, then `image_state` compares image ids and force-recreates only when no job runs. Result text says `image unchanged (cache hit)` / `image rebuilt, container recreated`.
- `delivery_doctor.py`: check `pool.<name>.files-current`.
- Outside `owns` (needed to print the plan lines and keep tests green): `delivery_ci_setup.py` (plan prints `<file>: differs from luismc-delivery <version>`), `tests/test_dl103_pool_keep_cap.py` (two expectations moved: text no longer says "rebuilt"; extra docker inspect calls).
- Docs: R13.84 in the delivery spec, change note, feature note.

## Tests
- `python3 -m unittest test_dl162_pool_refresh_files` (7 tests): OK
- pool tests incl. `test_runner_pool.py` (243 tests): OK
- doctor tests (33): OK
- `docs_check.py`: 0 errors, 0 warnings
NOT READY
