# DS235a report

Branch `DS235a-lifecycle-contract`. Code head: a9295b51e2e3f67e256594bedad943e0f8d9fe5a (the report commit follows it).

## Files
- `claude/plugins/docs/schemas/lifecycle.schema.json` (new, LC-1)
- `claude/plugins/docs/templates/design-system/lifecycle/lifecycle.json`, `words.json` (new starter)
- `claude/plugins/docs/templates/design-system/guards/words-lint-{typescript-vitest,rust,go,python}/` (new, LC-2, LC-31)
- `claude/plugins/docs/scripts/lifecycle_check.py` (new: `validate`, `setup --local-app yes|no`)
- `claude/plugins/docs/scripts/design_system.py`: one line, `init` skips the `lifecycle` template folder (else it landed in the layout and raised DS3)
- `claude/plugins/docs/skills/design-system-setup/SKILL.md`: lifecycle step only
- `claude/plugins/docs/references/docspec.md`: new R15.13 to R15.15
- `docs/features/docs/spec.md`: R5.21, R5.22 and proof rows
- Change notes: `docs/architecture/changes/DS235a-lifecycle-contract.md` (plugin), `DS235a-docspec-lifecycle.md` (docspec), `docs/features/docs/changes/DS235a.md`
- `claude/plugins/docs/tests/test_ds235a_lifecycle_contract.py`

## Tests
- `cd claude/plugins/docs/tests && python3 -m unittest test_ds235a_lifecycle_contract`: 23 tests OK. It runs the Go (`go test`), Rust (`cargo test`) and TypeScript forms (the `.test.ts` under node with a small vitest shim; vitest itself is not installed here).
- `python3 -m unittest test_design_system test_du13_install_update`: 1 error, the same on `main` (`test_templates_hold_no_project_specific_words` reads a binary template as UTF-8). Not caused by this branch.
- Go template: also `go vet` clean.

## Checks
- `python3 claude/plugins/docs/scripts/docs_check.py`: 2 errors. G1 `docs/llms.txt` stale: already stale on `main`, generated file, not committed. D9 `docs/work/` present: expected on an agent branch.
- `change_notes.py check`: see run in session (output above the report commit).

## Notes
- The words table lives in `lifecycle.json` under `words` (`banned`, `states`); `words.json` is the same table as a file.
- The schema reader is a small stdlib validator in `lifecycle_check.py` (no `jsonschema` here).

READY
