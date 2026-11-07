# Shared component templates (React and TypeScript)

Copied into a project by `design_system.py components --apply` (DOCSPEC R15.10). Opt-in: nothing here is copied by `init` or `guards`.

**Stack: React and TypeScript, web only.** There are no templates for other stacks yet.

| Component | Use it for | Files |
|---|---|---|
| `DatePicker` | Every date the user enters. A month grid, a month select, a year select, previous and next month buttons, and a typed entry. No keypad for dates. | `DatePicker.tsx`, `date-picker-logic.ts`, `date-picker.css`, `DatePicker.test.tsx` |
| `TimePicker` | Times of day and durations. `units="h"` (hours), `"hm"` (hours and minutes) or `"hms"` (hours, minutes and seconds). 24-hour by default; 12-hour by locale. | `TimePicker.tsx`, `time-picker-logic.ts`, `time-picker.css`, `TimePicker.test.tsx` |
| `NumberKeypad` | Counts, measures and codes only. | `NumberKeypad.tsx`, `number-keypad-logic.ts`, `number-keypad.css`, `NumberKeypad.test.tsx` |

Every choice also copies the shared files: `PickerIcon.tsx`, `picker-base.css` and `test-dom.ts`. `spec/` holds the section each component adds to `next-version/components.md`; it is not copied as code.

## How to install

```bash
S="${CLAUDE_PLUGIN_ROOT}/scripts/design_system.py"
python3 "$S" components                                   # dry run: lists the files and spec sections
python3 "$S" components --apply                           # all three, into src/ui/pickers
python3 "$S" components --only date-picker,time-picker --dest packages/ui/src --apply
```

Then:

1. Add `picker-base.css` and the CSS of each chosen component to the shared UI stylesheet. They read the `--ds-*` tokens of `tokens.md`; a project with other token names renames the `var(--ds-...)` uses once, in these files.
2. Export the components from the shared UI package.
3. Add the test dependencies if the project lacks them: `vitest`, `jsdom`, `react`, `react-dom`. The tests start with `// @vitest-environment jsdom`.
4. Check the new sections in `next-version/components.md` and the new rows of the "Component words" table in `content.md`. The command added both, with a `CHANGES.md` entry, and rebuilt the gallery, which draws each component.
5. With the enforcement kit, set `CONFIG` in `scripts/design/raw-inputs-scan.ts`. That guard proves starter rule UX-56: no native date, time or number input.

## Known limits

- `TimePicker` hours run from 0 to 23. There is no `maxHours`, so a duration of 24 hours or more cannot be entered.
- `NumberKeypad` has no minus key and no `allowNegative`.
- `DatePicker` shows the locale's long date in its header by default ("14 March 2009"). Pass `formatValue` to show the project's own format.

## What every template promises

- Tokens only: no raw colour, size or font. Each pressable part is at least `--ds-target-min` (44 px).
- A focus ring on keyboard focus (`:focus-visible`, `--ds-focus-width`, `--ds-color-focus`).
- Names for every control; the words are props (`labels`) with English defaults, so they can come from `content.md`.
- Keyboard: the date grid follows the WAI-ARIA APG date picker (arrows, Home, End, Page Up and Down); each time column is a spin button (Up, Down, Page Up and Down, Home, End); the keypad keys are one tab stop with arrow keys between them. Enter picks or finishes, Escape cancels.
- No overlay of its own: put a picker in the project's one dialog and sheet component when it should float.
- Pure logic in `*-logic.ts`, tested without a DOM; the components are tested in jsdom with React's `act`.
