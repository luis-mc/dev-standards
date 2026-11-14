# DL331 report

Branch: DL331-picker-strict-ts

## Files
- Templates (react-typescript/): DatePicker.tsx, DatePicker.test.tsx, date-picker-logic.ts, NumberKeypad.tsx, number-keypad-logic.ts, TimePicker.test.tsx, test-dom.ts, README.md (strict-flags line).
- claude/plugins/docs/tests/test_dl331_picker_strict.py (new guard).
- docs/features/docs/spec.md (R5.19 and test row); docs/features/docs/changes/DL331.md; docs/architecture/changes/DL331-picker-strict-ts.md.

## Fixes
- Optional `min`, `max`, `maxLength` in KeypadOptions now `?: number | undefined`.
- Indexed reads guarded (days[di], bits[i], test spin buttons, chips, weeks[0]).
- Index-signature reads use brackets (got['y'], dataset['keypadKey']).
- test-dom.ts: no `!` and no unbound `.set`; the descriptor setter is called as `desc.set.call`.
- DatePicker: the effect with the stale `eslint-disable` became a render-time state adjustment (`seenValue`); no effect, no dependency list. Same behaviour; the react-hooks `set-state-in-effect` rule also passes.

## Sandbox proof (scratch folder outside the repo; npm reachable)
Packages: typescript 5, react 18, eslint 9, typescript-eslint, eslint-plugin-react-hooks, vitest, jsdom. tsconfig: strict, exactOptionalPropertyTypes, noUncheckedIndexedAccess, noImplicitOverride, noPropertyAccessFromIndexSignature, jsx react-jsx. ESLint flat: recommendedTypeChecked + react-hooks recommended-latest, reportUnusedDisableDirectives error.
- Before: `npx tsc --noEmit` 32 errors; `npx eslint src` 2 errors (set-state-in-effect, unbound-method).
- After: `npx tsc --noEmit` exit 0; `npx eslint src` exit 0; `npx vitest run --environment jsdom` 3 files, 36 tests pass.

## Repo checks
- `python3 -I -m unittest discover -s claude/plugins/docs/tests`: 250 tests OK. The new guard fails on the pre-fix templates (4 failures) and passes now.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.

READY
