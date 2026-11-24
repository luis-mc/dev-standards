# UX rules

> **Starter.** Every item in the rule table is a starter item. Keep, change or delete each one before v1 is approved. The Core UX Principles below are binding and are not starter items.

## Core UX Principles

> **Binding.** These seven principles are not starter items. Do not delete or weaken them. Every UX rule below serves one of them.

Every screen of every app must be:

- **CORE-1 Consistent**: the same thing looks and behaves the same everywhere (same wizard, buttons and words for the same action).
- **CORE-2 Built from reused components** (shared UI package; no one-off variants; the duplication check stays green).
- **CORE-3 Clear**: one headline says where you are; plain words; never raw file paths or codes as the main text.
- **CORE-4 User-friendly and intuitive**: an action takes exactly what you see (never hidden items); no redundant buttons; nothing to decode.
- **CORE-5 Assertive**: one primary action per screen, labelled by what it does ("Import 8 files"), with its reason; say what happened and what comes next.
- **CORE-6 Guided**: a step-by-step path drawn as the wizard (a step bar on top, only the current step below it, Back and the one primary action at the bottom; done steps can be looked back at, later steps are greyed and not pressable); no dead ends.
- **CORE-7 Boxed sections are consistent and aligned**: boxed sections (cards) present their content the same way (title, fonts, the layout of their facts and their action); boxes that sit next to each other share one width and one height, in a grid that makes the best use of the horizontal and vertical space on desktop and phone (as many columns as fit, never one narrow column with empty space beside it), with clear, balanced spacing between them so no box or its shadow touches or overlaps the next; a card may span 2 columns only when its row stays full.

A UI change that fails any of these is not done. Every UI brief and PR body checks itself against them and cites the CORE IDs it checked.

## Starter rules

Every rule has an ID. A feature spec and the code cite the ID (`design system UX-1`); they do not copy the rule. Each rule names the guard test that proves it, or `none yet`. When you add a guard, write its path in the Guard column. Never reuse the ID of a deleted rule.

<!-- rule-table:start -->
| ID | Rule | Guard |
|---|---|---|
| UX-1 | **Consistent everywhere.** The same thing looks, reads and behaves the same on every screen. Details CORE-1. | none yet |
| UX-2 | **Reuse shared components.** A part that nearly fits is extended, never copied. Details CORE-2. | none yet |
| UX-3 | **One headline says where you are.** Use plain words. Never show a raw path or code as the main text. Details CORE-3. | none yet |
| UX-4 | **One primary action per screen.** It is labelled by what it does, and its reason is next to it. An action on a choice names the work and its count ("Rename 12 files"). With nothing chosen it is disabled and says what to do ("Tick the files to rename"). Details CORE-5. | none yet |
| UX-5 | **A guided flow is a wizard.** A step bar sits on top. Only the current step shows. Back and the one primary action sit at the bottom. Done steps can be viewed. Later steps are greyed. A wizard that changes something ends as UX-30 says. Details CORE-6. | none yet |
| UX-6 | **No dead ends.** Empty, failed and waiting states say what is going on and offer the next step. Details CORE-6. | none yet |
| UX-7 | **Never act on hidden items.** The count on an action is the count the user can see. Details CORE-4. | none yet |
| UX-8 | **Only buttons look like buttons.** Information never does. An action is never a plain link. Details CORE-4. | none yet |
| UX-9 | **Ask first in the page.** Use one question card: Cancel on the left, the action on the right. Never use the browser's alert, confirm or prompt. | none yet |
| UX-10 | **Boxed sections share one card look and sit in one grid.** Use as many columns as fit, with equal widths. Cards never touch. Details CORE-7. | none yet |
| UX-11 | **Long lists use the one shared pager.** A preview ends with "See all N".  The page size is 24, 48 or 96, chosen in the pager and remembered, and one size serves every list. The pager shows Previous, the page numbers and Next. There is no Load more, Show more or silent cap. | none yet |
| UX-12 | **Choice lists start with Select all N and Clear.**  On a list of several pages, Select all takes this page first ("Select all 24 on this page"); once the page is ticked it offers the rest ("Select all 214 files"). The count line says how many are ticked. | none yet |
| UX-13 | **A button that starts work is not pressable while it runs.** It says that it is running. Every button that sends a request stays busy until the answer. The busy state comes from the server's answer, not a timer. | none yet |
| UX-14 | **The core content comes first.** Secondary notices never push it down.  The top bar may shrink on scroll and the bottom bar stays. Chrome never pushes the core content below the fold. | none yet |
| UX-15 | **Use the width on wide screens.** Do not leave a narrow column in the middle of a wide page.  No page sets a maximum width on its own words, chip rows or columns. | none yet |
| UX-16 | **Every screen works from 360 px to desktop.** The page never scrolls sideways. Touch targets are at least 44 px. The next action is above the fold on a phone. | none yet |
| UX-17 | **Accessible.** Contrast meets WCAG 2.2 AA in every theme. Focus is always visible. Pages use landmarks and one h1. Motion respects prefers-reduced-motion. Every status and chart has a text equivalent.  Navigation text and links meet contrast in every theme. | none yet |
| UX-18 | **Dates, times and numbers are written one way.** Dates are year-month-day. Times are 24-hour, in local time. See content.md.  The same holds in exported files and file names. | none yet |
| UX-19 | **Running state is read from one source of truth.** A screen never sets its own flag for it. | none yet |
| UX-20 | **A field has its name above the box.** Help sits between the name and the box. Mark only optional fields. | none yet |
| UX-21 | **Mistakes are shown after the action button is pressed.** Each is shown above its box, and a list of all of them sits at the top of the form. | none yet |
| UX-22 | **Use the right control.** Use a switch for a setting that is saved at once. Use a check box for one that waits for Save. Use rows for up to 6 answers and a drop-down for 7 or more. | none yet |
| UX-23 | **Text boxes come in three widths.** Short, medium and full. The width hints at the size of the answer. | none yet |
| UX-24 | **A form ends like a wizard step.** Cancel is on the left, the one primary action on the right, both at the bottom. | none yet |
| UX-25 | **Use a table only to compare three or more facts.** Otherwise use rows. On a phone a row folds to two lines. Table column heads sort. | none yet |
| UX-26 | **Messages have four tones.** The tones are Done, Note, Needs you and Problem. A tone is never shown by colour alone. | none yet |
| UX-27 | **A button's result is one line under it.** There is one app-wide banner slot. | none yet |
| UX-28 | **Could not load says what, why and what next.** A fault in the page's own code is not a lost connection. It says "This page hit a fault." with the real error under Details. | none yet |
| UX-29 | **A wait names what is happening and shows a progress bar.** A known total is a filled bar. An unknown total is an animated bar. A wait on an outside limit says why and until when ("waits for the service's hourly limit until 08:34"). A count never sits still without a reason.  A job reports done out of total plus its stage. | none yet |
| UX-30 | **A wizard that changes something ends with three steps, in order: Review, then the work, then Done. There are no exceptions.** Review shows what will happen in numbers and words, and says "Nothing has changed yet." Earlier steps stay reachable, and Review counts again after a change. The work step is named by its own verb in the "-ing" form ("Moving") and shows live progress. Done shows what really happened, never the plan. A job under about a second opens Done at once. A job that is stopped or fails still ends at Done and says what was done and what is left. A read-only step before Review is named by what it reads ("Reading files"), never "Checking". The work step shows the item in hand, n of N and the time left, never a bare wait. It has no Back. A stored "running" with no live run reads Paused. Where this row names a state, it means one of the ten states of the wizard harness (loading, first-run, planning, ready-to-review, running, paused, stopped, failed, done, done-after-reload). Start again ends a wizard. Done and Stopped show Start again as the one primary. Only Start again begins a new run. Earlier steps are read-only. Details CORE-6. | none yet |
| UX-31 | **One search bar, always in the same place.** A page that finds things shows the bar, then the filter chips or toolbar, then the content, at the same distances. The bar has one small x inside the field that empties it and keeps focus. There is never a separate Clear button beside the field.  The toolbar order is fixed everywhere: filter box, chips, count line, then the view toggle. | none yet |
| UX-32 | **A map of pages draws every page.** It opens from one button, shows the current page, and a tile jumps to its page. It is never a list with a pager. | none yet |
| UX-33 | **A time axis has no pages.** Rows are grouped by period and load as they near the screen. The range shown is always named, and the reader can zoom or clear it. | none yet |
| UX-34 | **Running work shows in one strip.** Closed, it is one line with the lead job, a bar and the time left. It opens into the detail. A new or failed job opens it once. It reads the same source as UX-19. Background work never locks a step. A job that runs by itself shows as a line inside the step. The strip and the page read one progress value. | none yet |
| UX-35 | **Focus moves only when the user asks.** A refresh never moves the scroll or takes focus away. A dialog puts focus on its safe choice, and focus returns to the opener when it closes. | none yet |
| UX-36 | **Motion is short and has a purpose.** Durations and easing come from tokens. Under prefers-reduced-motion nothing moves. | none yet |
| UX-37 | **Buttons in a card sit at its bottom.** They are one per line and share the card's width. The screen's one primary stays in the action bar. Details CORE-7. | none yet |
| UX-38 | **Blocked actions say why.** A wrong value keeps the primary pressable and lists the mistakes (UX-21). A block that is not about a field shows the action disabled with its reason beside it. A wait is said once, in one line, from one function. No rows of locked buttons. | none yet |
| UX-39 | **A table export holds every row.** It is in the order shown, never only the page on screen. Text that looks like a formula is neutralised. The file is named for what it holds, then the date and time. | none yet |
| UX-40 | **Use a slider only for a number on a range.** It has a visible name and shows its value in words. It works with arrow keys, and its hit area is at least 44 px. A choice of a few named answers uses UX-22 instead. | none yet |
| UX-41 | **Show, don't only tell.** Use a picture where it helps: a chart for numbers over time, a bar for anything that runs. A picture supports the words beside it, never replaces the next action, and has a text equivalent (UX-17). | none yet |
| UX-42 | **An action bar puts its reason above the buttons.** While it works, the primary stays in place and says that it is running. A sticky foot never covers the content. Its height is reserved, so the last row ends above it on every screen size. Details CORE-5. | none yet |
| UX-43 | **One overlay, three forms.** A small screen gets a bottom sheet. A wider screen gets a centred dialog when the overlay changes data, or an anchored popover when it only changes the view. A screen never builds its own. | none yet |
| UX-44 | **An overlay has a title, a close button and one primary.** The title names it. The close button is at least 44 px. The footer holds Cancel on the left and the one primary action on the right. Only the body scrolls. | none yet |
| UX-45 | **A modal overlay traps focus and locks the page.** Tab stays inside it, the page behind is inert and does not scroll, and the page does not jump when the lock starts or ends. | none yet |
| UX-46 | **Escape closes an overlay.** It counts as Cancel. An overlay with unsaved input asks first (UX-9). A click outside closes a popover. | none yet |
| UX-47 | **An overlay is named for assistive technology.** It has role dialog, is labelled by its title, and sets aria-modal when it is modal. | none yet |
| UX-48 | **An overlay is never stacked on an overlay.** One opens at a time. A second step replaces the first, or becomes a page. | none yet |
| UX-49 | **The page scrolls, never a box inside it.** A frame is as tall as its section. Long lists use the pager. Only a wide table may scroll sideways inside its frame. The page itself never scrolls sideways (UX-16). | none yet |
| UX-50 | **Nothing is shown only on hover.** A menu or control is drawn at every width and for every pointer, mouse or touch. | none yet |
| UX-51 | **One shape per kind of card.** Same height, no small variant, long names stop at two lines. A state is said in words, never a bare colour frame. Details CORE-7. | none yet |
| UX-52 | **An overview only shows and links.** It has no command buttons. Each command lives in one place. Settings hold configuration only. Details CORE-4. | none yet |
| UX-53 | **"x ago" keeps ageing while the page stays open.** It reads one shared clock that pauses while the page is hidden and catches up when shown. | none yet |
| UX-54 | **A wizard's behaviour belongs to the shared wizard.** Current step, locks, Stop, busy and Done live in one part. A page passes data only. With the enforcement kit installed, its wizard harness (`scripts/design/wizard-behaviour.ts`) proves it; write that path in the Guard column then. | none yet |
| UX-55 | **A theme changes token values only, never a component.** A theme may change one named accent slot.  No colour literal or font family appears outside the tokens. | none yet |
| UX-56 | **Dates use the date picker, times use the time picker, and the number keypad is only for counts, measures and codes.** Never a native date, time or number input. With the enforcement kit installed, its raw-inputs guard (`scripts/design/raw-inputs.test.ts`) proves it; write that path in the Guard column then. | none yet |
| UX-57 | **One shared function names each kind of item.** No screen writes its own name. A title is never a file name: the file name sits on the quiet secondary line, also in search results, lists and histories. Where the screen's whole job is to list files, the file name is the title. An item with no readable name gets one shared stand-in. A year is added only when it is known. Details CORE-3. | none yet |
| UX-58 | **A background job works on change.** It does not walk everything again. With nothing to do it is not running and shows as done, in plain words, with the local date and time ("Done for all 1,200 files, 2026-10-28 21:27"). While it works it counts only that work ("3 of 12 new files"). A job held by a limit says why in its stage line. | none yet |
| UX-59 | **A brand motif is drawn by one shared part.** No screen draws its own copy. | none yet |
| UX-60 | **One tab row and one filter bar per page, at most.** A tab's count is drawn by one shared part. | none yet |
| UX-61 | **A companion app follows the main app's design.** A change asked for the companion that would hurt the main app is questioned, then refused or made companion-only, and the decision is recorded in the PR body. | none yet |
| UX-62 | **A Windows installer keeps the stock WixUI dialogs and gives them the product's artwork.** The banner (WixUIBannerBmp, 493x58) and the side picture (WixUIDialogBmp, 493x312) are drawn at build time from the design-system tokens, never with hand-picked colours. A second product gets its own variant, such as a black-and-white one, from its own tokens. Details: the installer artwork component. | none yet |
| UX-63 | **A Windows update runs in one native window.** It shows the steps Review, Downloading, Waiting for work to finish, Installing and Restarting, with progress, then Done. Cancel is shown where the updater supports it. The result is on its own Done step ("Now running 1.2.3"). There is never a separate message box. If the window must close for a restart, it reopens on Done in the same look. | none yet |
| UX-64 | **The update window looks like the product and fits its content.** It carries the product band and the product icon, never a generic icon. It is laid out from its content: no fixed pixel height, no scrollbar, nothing cut off. It ships with a layout check that runs at 100%, 150% and 200% text scale and fails when a control is clipped or a button is off the window. | none yet |
| UX-65 | **On macOS and Linux the update UI is the app's own web window.** It is in the design-system look and has the same steps and the same Done result as UX-63. An update that nobody asked for (nobody clicked Update) ends with one desktop toast with the product icon. Clicking it opens the Done step. It is never a modal box, on any system. | none yet |
| UX-66 | **A page's top level uses one component per layout role.** Page sections, card grid and form each have one shared component. A page never sets its own gap. The gap between sections is the section token. Rendered at 360, 393, 1300 and 1800 px, no box overlaps a neighbour, counting focus outline, glow and shadow with each field focused. No fixed px or rem in margin, padding or gap outside the token files. | none yet |
| UX-67 | **Install, update and remove screens use the shared lifecycle parts.** They use tokens only and the words of the lifecycle words table. Every state renders without clipping or overlap at 100% to 200% text scale and at 360 px. Remove stays disabled until the user chooses Keep my data or Delete my data too. | none yet |
| UX-68 | **The tray only notifies.** It never opens a modal or a Yes/No dialog, and shows one notice per event per 24 hours. A question goes to the one native question window, which is sized from its content. | none yet |
| UX-69 | **Notifications can open pages on the local server or the web app; those app pages have the actions.** A tray or OS notification has no action buttons. It carries a title, a short body and one click target. A click opens the right page of the local app or the web app, and that page holds the actions (for example "Pair again" and "Not now"). The lifecycle guard `tray-modal.mjs` checks it (LC-34). | none yet |
<!-- rule-table:end -->

## How to add a rule

- Give it the next free ID.
- Write one idea in plain, short words.
- Name the guard that proves it, or write `none yet`.
- Add a `CHANGES.md` entry.
