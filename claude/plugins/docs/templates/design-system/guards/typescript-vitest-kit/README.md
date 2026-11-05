# Design-system enforcement kit (TypeScript and Vitest)

Copied into `scripts/design/` by `design_system.py guards --stack typescript-vitest-kit --apply`.

**Stacks: TypeScript with Vitest only, for now (owner decision D243).** There are no templates for other stacks. A project on another stack ports the same checks by hand, or waits.

What is here:

- `no-app-css-scan.ts`, `no-app-css.test.ts`, `no-app-css.known.json`: no stylesheet, CSS-in-JS, layout `style=` or unknown class in app folders.
- `dom-layout.ts`, `dom-layout-judge.test.ts`, `dom-layout-example.spec.ts`: layout rules at 360, 393 and 1300 px, measured in the DOM (Playwright).
- `wizard-behaviour.ts`, `wizard-behaviour.test.ts`: every wizard is driven through ten required states (loading, first run, planning, ready to review, running, paused, stopped, failed, done, done after reload). A project may add states. It never drops one; the harness fails a driver that lists fewer.

Known-breach lists only shrink. A diff that adds an entry or raises a count fails `change_notes.py check`, except the change that first installs the list. No screenshot comparison anywhere.
