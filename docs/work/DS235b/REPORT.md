# DS235b report

## Files
- Parts (React): `claude/plugins/docs/templates/design-system/parts/react-typescript/` (UpdateBanner, UpdatesCard, UpdateHistory, RemoteUpdate, RemoveDialog, FleetRows, layout roles, words.ts, lifecycle-parts.css, tokens.fixture.css, one fixture per part, build-fixtures.mjs).
- Parts (Rust): `parts/rust/question_window.rs` (sizes to content), `parts/rust/tray_menu.rs` (notifies only, one notice per event per 24 h).
- Guards A-E: `guards/design-guards/` (rendered-layout, spacing-tokens, layout-roles, none-yet, citation-test, README).
- Lifecycle guards: `guards/lifecycle/` (tray-modal LC-22/LC-30, parts-tokens LC-23, states-render LC-24/LC-30).
- Docs: DOCSPEC R15.22 to R15.24 (gap of 10 after R15.12 left for DS235a's R15.13 to R15.21); spec R5.21 in docs/features/docs/spec.md; starter components 37-41, rules UX-66 to UX-68; change notes docs/architecture/changes/DS235b-lifecycle-ui.md and docs/features/docs/changes/DS235b.md.
- Tests: `tests/test_ds235b_guards.py`, `tests/test_ds235b_parts.py`, helper `tests/_ds235b.py`.
- Small edits outside the owned list, needed so existing tests pass: `scripts/design_system.py` (init skips the `parts` folder; GALLERY_SCRIPT_VERSION 2 to 3), `scripts/gallery_draw.py` (drawings for components 37-41), `tests/test_du13_install_update.py` (highest rule ID 65 to 68).

## Notes
- The words table (lifecycle/words.json, DS235a) did not exist yet. words.ts holds the contract defaults and loads the table at fixture build time when the file exists.
- Fixture apps are built with esbuild and react (installed in a temp folder by the tests, or DS_NODE_MODULES). Tests skip if that or Playwright is missing.
- The fixtures were run in the e2e sense: states-render and rendered-layout load every fixture page in Chromium at 360/393/1300/1800 px and 100/150/200% scale.
- Starter rules still say bare "none yet"; guard D will fail them in a project until it dates them (stated in the guards README).

## Tests
- `DS_NODE_MODULES=<node_modules with react, react-dom, esbuild> python3 -m unittest discover -s claude/plugins/docs/tests -p "test_ds235b_*.py"`: 46 tests, OK.
- `test_design_system.py` 38 OK; `test_components.py` 20 OK; `test_hooks.py` 16 OK; `test_du13_install_update.py` 9 OK; `test_dl331_picker_strict.py` 5 OK.
- `rustc --test` on both Rust models: 6 and 3 tests OK (also run by test_ds235b_parts).

## docs_check
`python3 claude/plugins/docs/scripts/docs_check.py`: 2 errors, both expected and not from this task's content:
- G1 docs/llms.txt stale: generated file, already stale on origin/main; not committed by a branch (AGENTS.md).
- W1 docs/work/DS235b/REPORT.md: work files live only on the branch; stripped before the join.

## Head SHA
Code head: 08a6dc948e7b37a2449040107bd96828fb898335 (this report is committed after it).

READY
