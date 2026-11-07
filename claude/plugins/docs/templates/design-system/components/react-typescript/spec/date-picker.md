## {{N}}. Date picker

- **Used for:** every date the user enters: a date of birth, a start date, moving something to another day. It replaces a native date input and a keypad for dates. Counts, measures and codes use the number keypad; times use the time picker.
- **Looks:** the field name and the chosen date in words over a rule; a row with previous and next month buttons around a month select and a year select; a month grid of day buttons with the weekday initials on top; and a typed entry under the grid. The chosen day is the primary fill. Today has a thicker edge. A day outside the range has a dashed edge.
- **Source:** `{{SOURCE}}/DatePicker.tsx` (logic in `date-picker-logic.ts`, styles in `date-picker.css` and `picker-base.css`)
- **Rules:** UX-16, UX-17, UX-20, UX-22, UX-43.
- **Guard:** the template's unit tests (`DatePicker.test.tsx`): keyboard, value and limits.

### Behaviour

- **Value.** An ISO day (`YYYY-MM-DD`) or nothing. A day is picked by pressing it, or by typing it and pressing Enter or leaving the box.
- **Bounds.** `min` and `max`. Days outside are disabled, the month buttons stop at the range, and the year select offers only the years in it. A typed day outside the range is refused with a line that names the range.
- **Typed entry.** Three numbers in the locale's order (`DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD`), separated by `/`, `.`, `-` or a space. A two-digit year and a day that does not exist are refused with a line that shows the pattern.
- **Shown value.** The header shows the chosen day through `formatValue`; pass the project's one date formatter so it matches content.md. Without it, the locale's long date is shown.
- **Locale.** Month and weekday names, the order of the typed numbers and the week start (Monday by default) follow the locale.
- **Where it opens.** Inline, or inside the project's one overlay component (a sheet on a phone, a popover or dialog on a wider screen) with Cancel and Done. It builds no overlay of its own.

### Keyboard and assistive tech

- The picker is a group named by its field name. The day grid is an ARIA grid with one tab stop (WAI-ARIA APG, date picker).
- Arrow keys move a day or a week. Home and End go to the start or end of the week. Page Up and Page Down change the month; with Shift, the year. Keys never leave the range.
- Enter or Space picks the focused day. Escape cancels when the picker sits in an overlay.
- Each day is named in full ("Saturday 14 March 2009"). Today is `aria-current="date"`. The chosen day is `aria-selected`.
- Every button, select and box is at least `--ds-target-min` square and shows the focus ring (`--ds-focus-width`, `--ds-color-focus`) on keyboard focus.

### Words (content.md)

"Previous month", "Next month", "Month", "Year", "Or type the date", "Type the date as {pattern}.", "Pick a date from {min} to {max}." A project changes them through the `labels` prop.
