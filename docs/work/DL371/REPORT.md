# DL371 report: versioned release asset names

## Files
- `templates/shared/.github/workflows/package-windows.yml`: new "Name the release assets" step. It writes `<installer_name>_<version>.msi` and `SHA256SUMS` in `release/`, and honours `release_assets.versioned_names`. The `windows-installer` artifact name is unchanged.
- `templates/{go,rust,dotnet}/.github/workflows/package.yml`: comment only (these upload CI artifacts, not release assets). The ts `package.yml` has no release-asset text and is unchanged.
- `templates/shared/scripts/delivery/windows-msi-linux.sh`: comment only. It is a CI check and its output is not a release asset.
- `references/release-asset-names.md` (new), `references/config-schema.json` (`release_assets.versioned_names`, default true).
- `docs/architecture/DELIVERYSPEC.md`: row DL-96. `invariants.md`: one line in §13.4.
- `docs/features/delivery-speed/spec.md`: R5.17, test row, `code:` entry.
- Change notes: DL371 plugin notes (delivery minor, project-setup patch), feature notes (delivery-speed, delivery, project-setup), DELIVERYSPEC note.
- `tests/test_dl371_versioned_asset_names.py` (new).

## Tests
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p test_dl371_versioned_asset_names.py`: OK, 7 tests.
- Existing tests of changed files (test_config, test_dl120, test_dl192, test_dl229, test_dl245, test_ds201): all OK.
- `python3 tools/test_delivery_windows.py`, `tools/test_smoke_packaged.py`: all passed.

## docs_check
`python3 claude/plugins/docs/scripts/docs_check.py`: two errors, both expected on a task branch. G1: `docs/docs-map.json` is generated and is not committed here (the release regenerates it; it also keeps the M1 warning about the new reference until then). W1: `docs/work/` files stay on this branch only. No other errors (T2 skipped, shallow clone).

Branch head: see `git rev-parse origin/DL371-versioned-asset-names`.

READY
