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

- **Used for:** a guided flow with a step bar on top, only the current step, and Back and the primary action at the bottom. A wizard that changes something ends with three steps, in order: Review, then the work (its own verb in the "-ing" form), then Done (UX-30). Review shows what will happen in numbers and words, and the line "Nothing has changed yet." Earlier steps stay reachable, and Review counts again after a change. Its one primary is named by the work and its count. The work step shows live progress and has no Back. Done shows what really happened, never the plan, and its one primary is the next action. A job under about a second opens Done at once. A stopped or failed job still ends at Done and says what was done and what is left. A step that only reads before Review is named by what it reads ("Reading files"), never "Checking".
- **Source:** `src/ui/wizard`
- **Rules:** UX-5, UX-4, UX-24, UX-30, UX-35.
- **Guard:** none yet.

## 5. Sticky action bar

- **Used for:** keeping the primary action in reach on a long page or a small screen. Its reason line sits above the buttons.
- **Source:** `src/ui/action-bar`
- **Rules:** UX-4, UX-14, UX-16, UX-42.
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
- **Rules:** UX-10, UX-1, UX-15, UX-37.
- **Guard:** none yet.

## 9. Dialog and sheet

- **Used for:** the one question card that asks first (Cancel left, the action right). A sheet is the same card sliding in on a small screen.
- **Source:** `src/ui/dialog`
- **Rules:** UX-9, UX-17, UX-16, UX-35.
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
- **Rules:** UX-25, UX-16, UX-17, UX-18, UX-39.
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
- **Rules:** UX-7, UX-12, UX-13, UX-38.
- **Guard:** none yet.

## 21. Search bar and find layout

- **Used for:** the search or filter bar, and the layout of a page that finds things: the bar, then the chips or toolbar rows, then the content, always in that order at the same distances. The bar has an icon, the field, and one small x inside the field that empties it and keeps focus.
- **Source:** `src/ui/search-bar`
- **Rules:** UX-31, UX-7, UX-16, UX-17.
- **Guard:** none yet.

## 22. Check box row

- **Used for:** one check box beside its label, with the explanation on its own line below. A choice that waits for Save uses it. A row tick and a filter chip use the same part with a hidden or styled label. It has a partial state (announced as mixed), an invalid state and a disabled state.
- **Source:** `src/ui/check-row`
- **Rules:** UX-22, UX-16, UX-17.
- **Guard:** none yet.

## 23. Slider

- **Used for:** choosing one value on a line by dragging or pressing. It has a visible name, a track and a handle, and the current value in words given by the caller. Arrow keys step by one, Page Up and Page Down by a tenth, Home and End go to the ends. On a phone the value sits above the track so a thumb never covers it.
- **Source:** `src/ui/slider`
- **Rules:** UX-40, UX-16, UX-17.
- **Guard:** none yet.

## 24. Time axis list

- **Used for:** things that happen over time, read as one axis. It has a range bar (the chosen range, Clear, zoom out and zoom in), a chart of the range with one bar per period, and the rows under a period header with its count. The range bar and the period header dock under the top bar while the rows scroll. An empty period says so and offers to widen the range. An error keeps the rows already drawn.
- **Source:** `src/ui/time-axis`
- **Rules:** UX-33, UX-6, UX-16, UX-18.
- **Guard:** none yet.

## 25. Page jump map

- **Used for:** jumping to any page of a long paged thing by seeing all of them. It is a grid of page tiles in reading order, each a small picture with its number. The current page is ringed and says "Now". A tile jumps there and closes the map. A page that cannot be drawn keeps its number and a quiet "No picture". It opens from one button as a sheet. On a phone there are four tiles across.
- **Source:** `src/ui/page-map`
- **Rules:** UX-32, UX-16, UX-17.
- **Guard:** none yet.

## 26. Live log

- **Used for:** a program's lines as they are written. It has a title, a Show choice (everything, warnings and errors, errors only), Follow new lines, a Full window button that grows the card over the page (Esc and "Back to normal size" shut it), and one quiet note on what is kept and that secrets are taken out. Each line has a time, the level written out, and the message. Lines come from one helper, so a job writes one started line, a progress line at most once a minute, and one finished line.
- **Source:** `src/ui/live-log`
- **Rules:** UX-16, UX-17, UX-35.
- **Guard:** none yet.

## 27. Activity strip

- **Used for:** the one place that says what runs now. Closed, it is one line: the label, one running mark, the lead job's name, its bar, the count and time left, "+K more", and a button "Show all N jobs". Open, the lead shows in full and the others are aligned rows. One job shows no button. The choice is remembered per person, and a missing store never breaks it. A new or failed job opens it once. The lead is the job that ends last.
- **Source:** `src/ui/activity-strip`
- **Rules:** UX-34, UX-19, UX-29, UX-17.
- **Guard:** none yet.

## 28. Dates, times and numbers

- **Used for:** the one formatter for every date, time, number, size, percent and time left. No screen builds its own string. The formats are in content.md.
- **Source:** `src/lib/format`
- **Rules:** UX-18.
- **Guard:** none yet.

## 29. Table export

- **Used for:** the Export button of a table. It writes every row in the order shown, neutralises text that looks like a formula, and names the file for what it holds, then the date and time. A page that offers it does not name the file format in its lead.
- **Source:** `src/ui/table-export`
- **Rules:** UX-39, UX-25, UX-18.
- **Guard:** none yet.

## 30. Picture card, grid and rail

- **Used for:** a thing that is a picture (a cover, a portrait, a photo) shown as a tile with its title and one quiet line. The whole tile is one link. A small badge may sit on the corner and a bar may show progress. Tiles sit in a grid that fills whole rows, or in one horizontal rail. A tile lifts a little on hover and focus, and never over the next tile. Placeholders keep the final size, so nothing moves while loading. Items that are not pictures are rows, not tiles.
- **Source:** `src/ui/picture-card`
- **Rules:** UX-10, UX-11, UX-8, UX-16, UX-36.
- **Guard:** none yet.

## 31. Chart with a text alternative

- **Used for:** numbers over time or in shares, drawn as inline SVG to scale, labelled, in token colours. Each chart has a text or table alternative. A chart shows the top N and then "See all N". Key numbers are lettered figures, never tiles.
- **Source:** `src/ui/chart`
- **Rules:** UX-41, UX-17, UX-18, UX-11.
- **Guard:** none yet.

## 32. Shared component rules

- **Used for:** the rules every component above follows. A component that breaks one is extended, never copied (UX-2).
- **Source:** `src/ui`
- **Rules:** UX-1, UX-2, UX-8, UX-13, UX-37.
- **Guard:** none yet.

| Component | Rule |
|---|---|
| Primary button | One per region. It is named by what it does. |
| Secondary button | Grouped in one actions row next to the primary. In a card, one per line at the card width. |
| Danger button | Always followed by the in-page question card (UX-9), never a browser box. |
| Link | Used for navigation, and inside running text. An action is never a plain link. |
| Metadata line | Quiet text with a middle dot between facts. Equal years collapse ("2015", not "2015-2015"). |
| Status text | Plain text, emphasis by weight. A warning is a quiet line with its action. |
| Tag | A small flat label with no hover and no focus. It never looks like a button. |
| Section | A heading with a hairline. No heavy boxes round ordinary content. |
| Panel | Only for a self-contained unit that needs framing. It is the one shared card. |
| Progress | A thin bar plus text ("page 12 of 24"), not a boxed chip. |
| Bulk action | Names its scope in the label ("Move all 12 files"), then a preview, then a question, then Undo. |

## 33. Other shared parts

- **Used for:** smaller parts that every screen shares. Reuse them, extend them, never copy them. The icon set: one set, and an icon beside a tone always has a word too (UX-26). The help line: one quiet line under a control, in a sentence that ends in a full stop. The compact row: one layout for an item and a group of items, with a 44 px tick target, a title on one line, one quiet second line, and at the end a size or a chevron that opens the group in place. The facts list: name and value pairs with a thin line between rows, each name above its value in a narrow card. The data hooks: the one way a screen loads and pages a list, so loading, empty and failed states are the same everywhere.
- **Source:** `src/ui`
- **Rules:** UX-2, UX-6, UX-8, UX-16, UX-17.
- **Guard:** none yet.

## How to add a component

- Give it the next number.
- Write the four lines: Used for, Source, Rules, Guard.
- Cite the UX rules it follows by ID.
- Add a `CHANGES.md` entry.
