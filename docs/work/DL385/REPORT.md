# DL385 report

One release-asset name for every project: `<Product>-<version>-<os>-<arch>.<ext>`.

## Files
- references/release-asset-names.md (rewritten; opt-out and CI-artifact sections kept)
- templates/shared/.github/workflows/package-windows.yml (PRODUCT, ARCH; name `${PRODUCT}-${version}-win-${ARCH}.msi`)
- templates/shared/scripts/delivery/lifecycle_release_check.py (os word, zip, product check)
- templates/shared/scripts/delivery/windows-msi-linux.sh, references/config-schema.json (wording)
- docs: DELIVERYSPEC DL-96 and DL-112 rows, lifecycle-contract.md, delivery-speed and lifecycle specs
- notes: architecture/changes/DL385-installer-names.md, features/delivery-speed/changes/DL385.md, features/lifecycle/changes/DL385.md
- tests: new test_dl385_installer_names.py; updated test_dl371_versioned_asset_names.py, test_ds235d_release_optout.py
- go, rust, dotnet, ts package.yml name no release asset (comments only), so no change.

## Tests
- `python3 -m unittest test_dl371_versioned_asset_names test_ds235d_release_optout test_dl385_installer_names` (in claude/plugins/delivery/tests): 34 tests OK.

## docs_check
`python3 claude/plugins/docs/scripts/docs_check.py`: one error, W1 for this file under docs/work/. Expected: AGENTS.md puts reports there on the branch only. No other findings. T2 skipped (shallow clone).

## Branch head
See `git rev-parse HEAD` of origin/DL385-installer-names (the commit after this report).

READY
