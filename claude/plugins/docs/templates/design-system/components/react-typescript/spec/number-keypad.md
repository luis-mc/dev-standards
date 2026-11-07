## {{N}}. Number keypad

- **Used for:** counts, measures and codes only: a number of repetitions, a weight, a distance, a quantity, a one-time code. Many quick entries in a row. Never for a date, a time or a duration: those use the date picker and the time picker. It replaces a native number input.
- **Looks:** the field name; the value in a large tabular figure in a box, with its unit after it; a 3 by 4 grid of keys (1 to 9, then ".", 0 and Delete last digit); a quiet reason line; then Clear, Cancel and Done in one row, Done the primary.
- **Source:** `{{SOURCE}}/NumberKeypad.tsx` (logic in `number-keypad-logic.ts`, styles in `number-keypad.css` and `picker-base.css`)
- **Rules:** UX-56, UX-16, UX-17, UX-20, UX-22, UX-43.
- **Guard:** the template's unit tests (`NumberKeypad.test.tsx`): keyboard, value and limits for a number and a code. With the enforcement kit, `scripts/design/raw-inputs.test.ts` bans a native number input (UX-56).

### Behaviour

- **Value.** Text, so a code keeps its leading zeros. `kind="number"` (default) or `kind="code"`.
- **First key.** It opens with the current value; the first key replaces it, as a native field does.
- **Limits.** `decimals` (0 has no "." key), `min`, `max` and `maxLength`. A key that would pass `max`, the decimals or `maxLength` is refused. Done is disabled below `min`, on an empty value, or on a code shorter than `maxLength`, and the reason line says why.
- **Known limit.** There is no minus key and no `allowNegative` prop: a negative number cannot be entered. Add it when a real need comes.
- **Where it opens.** Inline, or inside the project's one overlay component (a sheet on a phone). It builds no overlay of its own.

### Keyboard and assistive tech

- The keypad is a group named by its field name. The value is an `output` that is announced when it changes.
- Digits, "." and Backspace type from anywhere inside it. The keys are one tab stop; arrow keys move between them, Home and End go to the first and last key. Enter on a key presses it; Enter elsewhere is Done. Escape cancels.
- Every key and button is at least `--ds-target-min` high and shows the focus ring on keyboard focus.

### Words (content.md)

"Delete last digit", "Clear", "Cancel", "Done", "Type a number.", "The lowest is {min}.", "The highest is {max}.", "Type all {n} digits." `design_system.py components` adds each word that is not there yet to the Component words table of content.md. A project changes them there and passes them through the `labels` prop.
