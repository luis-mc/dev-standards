# Design-system enforcement kit (TypeScript and Vitest)

Copied into `scripts/design/` by `design_system.py guards --stack typescript-vitest-kit --apply`.

**Stacks: TypeScript with Vitest only, for now (owner decision D243).** There are no templates for other stacks. A project on another stack ports the same checks by hand, or waits.

What is here:

- `no-app-css-scan.ts`, `no-app-css.test.ts`, `no-app-css.known.json`: no stylesheet, CSS-in-JS, layout `style=` or unknown class in app folders.
- `dom-layout.ts`, `dom-layout-judge.test.ts`, `dom-layout-example.spec.ts`, `layout.known.json`: layout rules at 360, 393 and 1300 px, measured in the DOM (Playwright).
- `wizard-behaviour.ts`, `wizard-behaviour.test.ts`, `wizard-behaviour.known.json`: every wizard is driven through ten required states (loading, first run, planning, ready to review, running, paused, stopped, failed, done, done after reload). A project may add states. It never drops one; the harness fails a driver that lists fewer.
- `raw-controls-scan.ts`, `raw-controls.test.ts`, `raw-controls.known.json`: no raw `<button>`, `<input>`, `<select>` or `<textarea>` in app code; apps use the shared UI components. Test files and the shared UI folders are not judged. How to install: copy the three files to `scripts/design/` (the `guards` command does), set `CONFIG` in `raw-controls-scan.ts` (app paths, shared UI paths, file globs), and run the test with Vitest.
- `contrast.ts`, `contrast.test.ts`, `contrast.known.json`: every text-on-fill token pair (`--ds-color-X` with `--ds-color-on-X`) meets WCAG 2.2 AA (4.5:1) in the light theme, the dark theme and any `[data-theme=NAME]` theme. A theme inherits what it does not set from `:root`. A translucent colour is reported as "cannot judge". How to install: copy the three files to `scripts/design/` (the `guards` command does), set `CONFIG` in `contrast.ts` (token file path, token prefix), and run the test with Vitest.

Known-breach lists (the `*.known.json` files, all read by the kit's tests) only shrink. A diff that adds an entry or raises a count fails `change_notes.py check`, except the change that first installs the list. No screenshot comparison anywhere.
