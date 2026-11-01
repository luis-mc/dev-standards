# Components

> **Starter.** Every item in this file is a starter item. Keep, change or delete each one before v1 is approved.

One numbered section per shared component. A part that nearly fits is extended with its section, never copied (UX-2). Each section has the same four lines. The Source paths are placeholders: replace them with the real export path or file.

## 1. Page header

- **Used for:** the headline that says where you are, with an optional line below it and the page's one primary action.
- **Source:** `src/ui/page-header`
- **Rules:** UX-3, UX-4, UX-17.
- **Guard:** none yet.

## 2. Top menu and breadcrumbs

- **Used for:** moving between the main areas, and showing the path back up.
- **Source:** `src/ui/top-menu`
- **Rules:** UX-1, UX-3, UX-16, UX-17.
- **Guard:** none yet.

## 3. Tabs

- **Used for:** switching between views of the same thing. A tab never starts work.
- **Source:** `src/ui/tabs`
- **Rules:** UX-1, UX-8, UX-17.
- **Guard:** none yet.

## 4. Wizard

- **Used for:** a guided flow with a step bar on top, only the current step, and Back and the primary action at the bottom.
- **Source:** `src/ui/wizard`
- **Rules:** UX-5, UX-4, UX-24.
- **Guard:** none yet.

## 5. Sticky action bar

- **Used for:** keeping the primary action in reach on a long page or a small screen.
- **Source:** `src/ui/action-bar`
- **Rules:** UX-4, UX-14, UX-16.
- **Guard:** none yet.

## 6. Action rows

- **Used for:** a list where each row has a name, a short line of facts and its own action.
- **Source:** `src/ui/action-row`
- **Rules:** UX-8, UX-25, UX-16.
- **Guard:** none yet.

## 7. Buttons

- **Used for:** every action. Primary, secondary and quiet styles. A running button is not pressable and says it is running.
- **Source:** `src/ui/button`
- **Rules:** UX-4, UX-8, UX-13, UX-16.
- **Guard:** none yet.

## 8. Card, card grid and facts list

- **Used for:** a boxed section; the grid that lays cards out; and a short list of name and value pairs inside a card.
- **Source:** `src/ui/card`
- **Rules:** UX-10, UX-1, UX-15.
- **Guard:** none yet.

## 9. Dialog and sheet

- **Used for:** the one question card that asks first (Cancel left, the action right). A sheet is the same card sliding in on a small screen.
- **Source:** `src/ui/dialog`
- **Rules:** UX-9, UX-17, UX-16.
- **Guard:** none yet.

## 10. Pager

- **Used for:** moving through a long list. A preview ends with "See all N".
- **Source:** `src/ui/pager`
- **Rules:** UX-11, UX-7.
- **Guard:** none yet.

## 11. List toolbar

- **Used for:** search, filters, the count, and the grid or list toggle above a list.
- **Source:** `src/ui/list-toolbar`
- **Rules:** UX-7, UX-11, UX-16.
- **Guard:** none yet.

## 12. Segmented choices and filter chips

- **Used for:** picking one of a few views (segmented), or turning filters on and off (chips).
- **Source:** `src/ui/segmented`
- **Rules:** UX-8, UX-17, UX-22.
- **Guard:** none yet.

## 13. One-choice list

- **Used for:** picking one answer from rows (up to 6) or a drop-down (7 or more). A multi-choice list starts with Select all N and Clear.
- **Source:** `src/ui/choice-list`
- **Rules:** UX-12, UX-22, UX-7.
- **Guard:** none yet.

## 14. Form field family

- **Used for:** a field (name, help, box, error), a toggle (saved at once) and a check box (waits for Save). Boxes come in three widths.
- **Source:** `src/ui/field`
- **Rules:** UX-20, UX-21, UX-22, UX-23, UX-24.
- **Guard:** none yet.

## 15. Tables and list rows

- **Used for:** a table to compare three or more facts; rows for everything else. Rows fold to two lines on a phone. Column heads sort.
- **Source:** `src/ui/table`
- **Rules:** UX-25, UX-16, UX-17, UX-18.
- **Guard:** none yet.

## 16. Progress bar

- **Used for:** a wait. Filled when the total is known, animated when it is not. It always names what is happening.
- **Source:** `src/ui/progress`
- **Rules:** UX-29, UX-17, UX-19.
- **Guard:** none yet.

## 17. Badges and counts

- **Used for:** a short status word or number next to a name. A badge is information: it never looks like a button.
- **Source:** `src/ui/badge`
- **Rules:** UX-8, UX-26, UX-17.
- **Guard:** none yet.

## 18. Messages and banner

- **Used for:** the four tones (Done, Note, Needs you, Problem); a button's one-line result; and the one app-wide banner slot.
- **Source:** `src/ui/message`
- **Rules:** UX-26, UX-27, UX-14, UX-17.
- **Guard:** none yet.

## 19. Empty, failed and error states

- **Used for:** a place with nothing to show, something that failed, or content that could not load. It says what, why and what next.
- **Source:** `src/ui/state`
- **Rules:** UX-6, UX-28, UX-3.
- **Guard:** none yet.

## 20. Selection bar

- **Used for:** acting on the items the user selected. It shows the count of what is selected and visible.
- **Source:** `src/ui/selection-bar`
- **Rules:** UX-7, UX-12, UX-13.
- **Guard:** none yet.

## How to add a component

- Give it the next number.
- Write the four lines: Used for, Source, Rules, Guard.
- Cite the UX rules it follows by ID.
- Add a `CHANGES.md` entry.
