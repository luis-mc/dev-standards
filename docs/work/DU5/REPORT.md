# DU5 report

## Built
Two new guard templates in `claude/plugins/docs/templates/design-system/guards/typescript-vitest-kit/`:
- `raw-controls-scan.ts`, `raw-controls.test.ts`, `raw-controls.known.json` (G1).
- `contrast.ts`, `contrast.test.ts`, `contrast.known.json` (G2).
README: two new bullets, each with a "How to install" line. `design_system.py` is unchanged: `guards` copies the whole kit folder, so the new files are copied already.
`tools/test_ds_enforcement.py`: the new test files run under the Node shim; the copy test and the empty-known-list test cover the new files.
Notes: `docs/architecture/changes/DU5-docs.md`, `docs/features/docs/changes/DU5.md`.

## Self-tests
raw-controls: planted raw button fails; all four tags found, components ignored; listed breach passes; fixed-but-listed fails; raised count fails; shared-path file ignored; test files ignored; other file types ignored.
contrast: WCAG ratios and colour parsing; passing pair (tint pairs too); failing pair; listed gap passes, new gap fails, worse ratio fails; fixed-but-listed fails; theme inherits a value from `:root`; `[data-theme=NAME]` and `var()`; translucent colour is "cannot judge".

## Commands
- `python3 -I tools/test_ds_enforcement.py`: 33 passed, 0 failed.
- `python3 tools/ci_areas.py --branch-advice`: "light: test locally only".
- `python3 claude/plugins/docs/scripts/docs_check.py`: 1 error, 1 warning. Both are not from this branch: G1 `docs/architecture/decisions.md` is a stale generated file (not edited, per the rules), and T2 on `features/test-cost`.

## Notes
Missing tokens file: `readGaps` returns no gaps, like an absent app folder in no-app-css. Set `CONFIG.tokensPath`.

Branch head SHA: see the final commit on `DU5-guard-templates`.

READY
