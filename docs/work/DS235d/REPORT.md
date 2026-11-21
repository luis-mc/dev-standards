# DS235d report

## Files
- claude/plugins/delivery/templates/lifecycle/os/: os-common.sh, linux-common.sh, linux-deb.sh, linux-rpm.sh, macos.sh, windows.ps1, leftovers-linux.sh, leftovers-macos.sh, leftovers.ps1, lifecycle-lanes.yml
- templates/shared/scripts/delivery/lifecycle_release_check.py, lifecycle_optout.py
- scripts/hook_session_start.py: one line "Lifecycle checks off: ..." (only when an opt-out is set)
- docs/architecture/DELIVERYSPEC.md section 1b: DL-109 to DL-113 (gap after DL-99, so DS235c fits in DL-100 to DL-108)
- docs/features/delivery-speed/spec.md: R5.25 to R5.27, proof rows, code map
- change notes: docs/architecture/changes/DS235d-lifecycle-os-steps.md, docs/features/delivery-speed/changes/DS235d.md
- tests: test_ds235d_os_steps.py, test_ds235d_release_optout.py

## Tests
- python3 -m unittest test_ds235d_os_steps test_ds235d_release_optout (in claude/plugins/delivery/tests): 31 tests OK, 2 skipped (shellcheck and pwsh not installed here; bash -n ran on every script).
- hook tests (test_dl109, dl118, dl151, dl96, test_load, test_questions): OK.
- Not run: PowerShell parse (no pwsh), shellcheck, the real OS steps (need a machine per lane; steps are tested with mocked service tools).
- ci_areas advice was a heavy workflow run; the brief forbids starting workflows, so it was not run.

## Notes
- tools.json: nothing registered. It holds pinned downloads with checksums; no new pinned tool is added.
- lifecycle.json keys the steps read (the schema from DS235a was not on main yet): product, targets, keep_on_remove, paths.{config,data,logs,install,service,console_port,data_roots,legacy_data,listen_ports,uninstaller,product_code,pkg_id,launchd_label,app,system_user}, test_interface.{selftest,pair,tray_start}.
- Lane result match key: lane (distro or os), arch, package.

## docs_check
python3 claude/plugins/docs/scripts/docs_check.py: 2 errors, both not from this change. G1 docs/llms.txt stale (also stale on the base without my changes; generated files are not edited by rule). W1 is this report under docs/work/ (stays on the branch only).

Branch head before this report commit: d02a1ac

READY
