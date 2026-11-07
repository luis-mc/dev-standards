## {{N}}. Time picker

- **Used for:** times of day and durations. `units` sets the columns: `h` for an hour setting, `hm` for a time of day such as a reminder, `hms` for a duration such as a rest or a timed hold. It replaces a native time input and a keypad for times.
- **Looks:** the field name and the value over a rule; then one column per unit, each an up key, the number in a large tabular figure, and a down key, with ":" between columns. A 12-hour locale adds an AM/PM switch after the last column. An optional row of quick-pick chips sits below; the chip that matches the value is pressed.
- **Source:** `{{SOURCE}}/TimePicker.tsx` (logic in `time-picker-logic.ts`, styles in `time-picker.css` and `picker-base.css`)
- **Rules:** UX-56, UX-16, UX-17, UX-20, UX-22, UX-43.
- **Guard:** the template's unit tests (`TimePicker.test.tsx`): keyboard, value and limits for `h`, `hm` and `hms`. With the enforcement kit, `scripts/design/raw-inputs.test.ts` bans a native time input (UX-56).

### Behaviour

- **Value.** Always 24-hour text: `HH`, `HH:MM` or `HH:MM:SS` by `units`. The 12-hour clock is display only.
- **Clock.** 24-hour by default; 12-hour when the locale's clock is 12-hour, or when `hourCycle="h12"` is set.
- **Steps.** `step` sets the minute and second step (5 for a reminder). Hours step by 1. A value off the step snaps to the next step.
- **Limits.** Hours 0 to 23, minutes and seconds 0 to 59. Up and Down wrap (23 to 00).
- **Known limit.** There is no `maxHours` prop: a duration of 24 hours or more cannot be entered. Add it when a real need comes.
- **Where it opens.** Inline, or inside the project's one overlay component with Cancel and Done. On a dense settings screen the quick picks may also sit under the closed field.

### Keyboard and assistive tech

- The picker is a group named by its field name. Each number is a `spinbutton` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and `aria-valuetext` ("30 minutes") (WAI-ARIA APG, spinbutton).
- Up and Down change the value by the step. Page Up and Page Down by 3 hours, 15 minutes or 15 seconds. Home and End go to the lowest or highest value. Left and Right move between columns.
- Enter is Done and Escape cancels, when the caller passes `onDone` and `onCancel`.
- The up and down keys are for touch and pointer; they are out of the tab order because the keyboard already steps the number. Each is at least `--ds-target-min` square and named ("More minutes").

### Words (content.md)

"Hours", "Minutes", "Seconds", "More {unit}", "Fewer {unit}", "Morning or afternoon", "Quick picks", "{n} hours", "{n} minutes", "{n} seconds". The AM and PM words come from the locale. `design_system.py components` adds each word that is not there yet to the Component words table of content.md. A project changes the others there and passes them through the `labels` prop.
