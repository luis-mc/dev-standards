# DL329 report

## Files
- `claude/plugins/delivery/templates/rust/scripts/delivery/rust_ci.py`: `link_target`, `_make_link` (symlink; junction on Windows via `_winapi` or `mklink /J`), `_remove_link`, `_exclude_link`; `target_cache_env` exports `DELIVERY_RUST_TARGET`.
- `claude/plugins/delivery/tests/test_dl329_rust_target_link.py` (8 tests).
- `docs/features/delivery/spec.md`: R5.61 and a test-table row.
- `docs/features/delivery/changes/DL329.md`, `docs/features/delivery-speed/changes/DL329.md`, `docs/architecture/changes/DL329-rust-target-link.md` (plugin, patch).

## Deviations
- `docs/features/rust-ci/` does not exist. The rust_ci spec text is delivery R5.50, so R5.61 is there. `docs_check` also maps rust_ci.py to delivery-speed, so it has a note too. runner-pool was not touched.
- No `.gitignore` template exists. A `target/` line does not match a link, so the link adds `/target` to `.git/info/exclude`.

## Tests
- `python -m unittest test_dl329_rust_target_link test_ds200_rust_ci test_dl295_rust_scope` (in the tests folder): 46 tests, OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.
- Windows junction path is covered by a mocked test only, not run on Windows.

## Branch head
Code commit 835ae8aca5291fe3189c997e767c1609f649cb55 on `DL329-rust-target-link` (this report is pushed in the next commit).

READY
