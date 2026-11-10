# DL173 report

## What changed
- `project_artifacts.py`: `schema_gate` and `schema_warnings`. The ledger reader (schema known: 1) and the ci-runs reader (known: 1) return empty/None as before when the schema is missing (ledger) or newer, and record one warning. `check` and `pending` print it (`--json` adds `warnings`). An absent file stays silent.
- Deviation: the ci-runs writer sets no `schema` field today, so for ci-runs only a newer schema warns; a missing one passes. Otherwise every real ci-runs file would warn.
- `references/plugin-compat.json`: three pairs, each with a `why`. Plugins are named, never folder paths.
- `delivery_doctor.py`: check `plugins` (`plugins.compat`). It reads the plugin cache (`DELIVERY_PLUGIN_CACHE` overrides the root), takes the highest version, warns (never fails) per unfit pair with `claude plugin update <plugin>@dev-standards`. No row when nothing to say.
- Change notes: `docs/architecture/changes/DL173-artifacts.md`, `DL173-delivery.md`; feature notes `docs/features/{artifacts,delivery}/changes/DL173.md`.
- Feature spec text not edited (T2 warning on artifacts). Wiring of `tools/test_artifacts_dl173.py` is left for the join.

## Tests
- `python -I tools/test_artifacts_dl173.py`: 8 passed, 0 failed
- `cd claude/plugins/delivery/tests && python -m unittest test_dl173_compat test_doctor test_ds202_rust_doctor`: 40 tests OK
- `python -I tools/test_project_artifacts.py`: see below
- `python3 claude/plugins/docs/scripts/docs_check.py`: G1 (generated decisions.md stale, expected), M1 and T2 warnings

