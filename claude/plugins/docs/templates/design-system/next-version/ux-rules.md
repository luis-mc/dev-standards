# UX rules

> **Starter.** Every item in this file is a starter item. Keep, change or delete each one before v1 is approved.

Every rule has an ID. A feature spec and the code cite the ID (`design system UX-1`); they do not copy the rule. Each rule names the guard test that proves it, or `none yet`. When you add a guard, write its path in the Guard column. Never reuse the ID of a deleted rule.

<!-- rule-table:start -->
| ID | Rule | Guard |
|---|---|---|
| UX-1 | **Consistent everywhere.** The same thing looks, reads and behaves the same on every screen. | none yet |
| UX-2 | **Reuse shared components.** A part that nearly fits is extended, never copied. | none yet |
| UX-3 | **One headline says where you are.** Use plain words. Never show a raw path or code as the main text. | none yet |
| UX-4 | **One primary action per screen.** It is labelled by what it does, and its reason is next to it. | none yet |
| UX-5 | **A guided flow is a wizard.** A step bar sits on top. Only the current step shows. Back and the one primary action sit at the bottom. Done steps can be viewed. Later steps are greyed. A wizard that changes something ends as UX-30 says. | none yet |
| UX-6 | **No dead ends.** Empty, failed and waiting states say what is going on and offer the next step. | none yet |
| UX-7 | **Never act on hidden items.** The count on an action is the count the user can see. | none yet |
| UX-8 | **Only buttons look like buttons.** Information never does. An action is never a plain link. | none yet |
| UX-9 | **Ask first in the page.** Use one question card: Cancel on the left, the action on the right. Never use the browser's alert, confirm or prompt. | none yet |
| UX-10 | **Boxed sections share one card look and sit in one grid.** Use as many columns as fit, with equal widths. Cards never touch. | none yet |
| UX-11 | **Long lists use the one shared pager.** A preview ends with "See all N". | none yet |
| UX-12 | **Choice lists start with Select all N and Clear.** | none yet |
| UX-13 | **A button that starts work is not pressable while it runs.** It says that it is running. | none yet |
| UX-14 | **The core content comes first.** Secondary notices never push it down. | none yet |
| UX-15 | **Use the width on wide screens.** Do not leave a narrow column in the middle of a wide page. | none yet |
| UX-16 | **Every screen works from 360 px to desktop.** The page never scrolls sideways. Touch targets are at least 44 px. | none yet |
| UX-17 | **Accessible.** Contrast meets WCAG 2.2 AA in every theme. Focus is always visible. Pages use landmarks and one h1. Motion respects prefers-reduced-motion. Every status and chart has a text equivalent. | none yet |
| UX-18 | **Dates, times and numbers are written one way.** Dates are year-month-day. Times are 24-hour, in local time. See content.md. | none yet |
| UX-19 | **Running state is read from one source of truth.** A screen never sets its own flag for it. | none yet |
| UX-20 | **A field has its name above the box.** Help sits between the name and the box. Mark only optional fields. | none yet |
| UX-21 | **Mistakes are shown after the action button is pressed.** Each is shown above its box, and a list of all of them sits at the top of the form. | none yet |
| UX-22 | **Use the right control.** Use a switch for a setting that is saved at once. Use a check box for one that waits for Save. Use rows for up to 6 answers and a drop-down for 7 or more. | none yet |
| UX-23 | **Text boxes come in three widths.** Short, medium and full. The width hints at the size of the answer. | none yet |
| UX-24 | **A form ends like a wizard step.** Cancel is on the left, the one primary action on the right, both at the bottom. | none yet |
| UX-25 | **Use a table only to compare three or more facts.** Otherwise use rows. On a phone a row folds to two lines. Table column heads sort. | none yet |
| UX-26 | **Messages have four tones.** The tones are Done, Note, Needs you and Problem. A tone is never shown by colour alone. | none yet |
| UX-27 | **A button's result is one line under it.** There is one app-wide banner slot. | none yet |
| UX-28 | **Could not load says what, why and what next.** | none yet |
| UX-29 | **A wait names what is happening and shows a progress bar.** A known total is a filled bar. An unknown total is an animated bar. | none yet |
| UX-30 | **A wizard that changes something ends with three steps, in order: Review, then the work, then Done. There are no exceptions.** Review shows what will happen in numbers and words, and says "Nothing has changed yet." Earlier steps stay reachable, and Review counts again after a change. The work step is named by its own verb in the "-ing" form ("Moving") and shows live progress. Done shows what really happened, never the plan. A job under about a second opens Done at once. A job that is stopped or fails still ends at Done and says what was done and what is left. A read-only step before Review is named by what it reads ("Reading files"), never "Checking". | none yet |
| UX-31 | **One search bar, always in the same place.** A page that finds things shows the bar, then the filter chips or toolbar, then the content, at the same distances. The bar has one small x inside the field that empties it and keeps focus. There is never a separate Clear button beside the field. | none yet |
| UX-32 | **A map of pages draws every page.** It opens from one button, shows the current page, and a tile jumps to its page. It is never a list with a pager. | none yet |
| UX-33 | **A time axis has no pages.** Rows are grouped by period and load as they near the screen. The range shown is always named, and the reader can zoom or clear it. | none yet |
| UX-34 | **Running work shows in one strip.** Closed, it is one line with the lead job, a bar and the time left. It opens into the detail. A new or failed job opens it once. It reads the same source as UX-19. | none yet |
| UX-35 | **Focus moves only when the user asks.** A refresh never moves the scroll or takes focus away. A dialog puts focus on its safe choice, and focus returns to the opener when it closes. | none yet |
| UX-36 | **Motion is short and has a purpose.** Durations and easing come from tokens. Under prefers-reduced-motion nothing moves. | none yet |
| UX-37 | **Buttons in a card sit at its bottom.** They are one per line and share the card's width. The screen's one primary stays in the action bar. | none yet |
| UX-38 | **Blocked actions say why.** A wrong value keeps the primary pressable and lists the mistakes (UX-21). A block that is not about a field shows the action disabled with its reason beside it. | none yet |
| UX-39 | **A table export holds every row.** It is in the order shown, never only the page on screen. Text that looks like a formula is neutralised. The file is named for what it holds, then the date and time. | none yet |
| UX-40 | **Use a slider only for a number on a range.** It has a visible name and shows its value in words. It works with arrow keys, and its hit area is at least 44 px. A choice of a few named answers uses UX-22 instead. | none yet |
| UX-41 | **Show, don't only tell.** Use a picture where it helps: a chart for numbers over time, a bar for anything that runs. A picture supports the words beside it, never replaces the next action, and has a text equivalent (UX-17). | none yet |
| UX-42 | **An action bar puts its reason above the buttons.** While it works, the primary stays in place and says that it is running. | none yet |
<!-- rule-table:end -->

## How to add a rule

- Give it the next free ID.
- Write one idea in plain, short words.
- Name the guard that proves it, or write `none yet`.
- Add a `CHANGES.md` entry.
