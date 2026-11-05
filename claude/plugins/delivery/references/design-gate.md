# Design-system enforcement as a required check (DL-92)

For a project that uses the `luismc-docs` design system and has copied the enforcement kit (`design_system.py guards --stack typescript-vitest-kit --apply`). The kit has three tests: no app CSS, DOM layout at 360, 393 and 1300 px, wizard behaviour. Each has a known list that only shrinks.

This page says where those tests run so that a breach cannot merge. It adds no new CI option; it uses the gate and the CI the project already has.

## Where each test runs

| Test | Needs | Runs in |
|---|---|---|
| No app CSS (source scan) | node only, seconds | the branch gate `guards` step, the pre-push hook, CI |
| Wizard behaviour | a component test runner (jsdom) or stubbed pages, under a minute | the branch gate `unit` step (changed packages), CI |
| DOM layout | a browser (Playwright) | the branch gate `e2e` step when a UI path changed, CI |

The branch gate is the agent's proof. CI on the ready PR is the merge gate. A breach is caught twice, once before the push and once before the merge.

## 1. In the branch gate (`scripts/delivery/gate.json`)

The scan and the self-tests of the kit are guard tests: put them in the project's `guards` project (the step that already runs with `"scope": "always", "pre_push": true`). Nothing to add if the guard project includes `scripts/design/*.test.ts`.

If the project wants the kit as its own, named step (the gate summary then says "design kit failed"), add:

```json
{"name": "design-kit", "scope": "always", "pre_push": true,
 "run": "pnpm vitest run --project guard scripts/design/no-app-css.test.ts scripts/design/wizard-behaviour.test.ts scripts/design/dom-layout-judge.test.ts"}
```

and put `"design-kit"` after `"guards"` in `fail_fast_order`. The DOM layout specs are ordinary e2e specs, so the `e2e` step (`ui-changed` scope) already runs them when `ui_paths` changed.

## 2. In CI (all options)

The kit's tests are ordinary tests of the project, so they run in whichever CI option the project picked (self-hosted runner, hosted runner, or the cloud sessions of Option 3). Two things only:

1. **Scope.** In `scripts/delivery/ci-scope.json`, a change under the app folders, the shared UI package or `docs/design-system/` must select the kit's tests (they are cheap, so select them whenever a UI path changed). The scan does not depend on which files changed, so it also belongs in the "always" set.
2. **Required.** The job that runs the kit must be a required status check on the default branch (a ruleset or branch protection setting; the owner sets it, the plugin never changes repository settings). The merge step already waits on `ci_watch.py` for the head commit's workflow runs (DL-07); keep the kit's job in a workflow listed in `watcher.ci_workflows` so a red kit keeps the PR from going green.

On Option 3 (statuses-only token), the cloud session posts one status per shard; name the kit's shard `design-kit` and list it in the ruleset's required contexts.

## 3. Edit-time hook and ratchet rules (what a reviewer checks)

- `hook_design_edit.py` (PreToolUse on Edit, MultiEdit and Write) warns on the first edit in a turn that adds CSS or a hand-made part (a check fires only when its matches increase; the warning carries no permission decision, so the normal permission prompt still applies; test files are skipped) under `design_system.app_paths` (default `apps/`) and denies a repeat in the same turn. Paths outside `design_system.shared_paths` (default `packages/ui/`) only. It is the early guard; the tests above are the gate.
- A known list (`no-app-css.known.json`, `layout.known.json`, `wizard-behaviour.known.json`) may lose entries in any change. It may gain an entry only in the change that first installs the kit, and every entry names the task that removes it.
- A diff that adds or raises an entry elsewhere fails. `change_notes.py check` enforces it for all three JSON lists (`known_lists`, default `scripts/design/*.known.json`): a list that exists at the base and gains an entry or a higher `count` is an offence; a list that is new at the base is the install change and passes. The kit's tests read all three lists from `scripts/design/`.
- Weakening a check to pass (a looser tolerance, a skipped state, a wider selector) is a design-system change and follows the order of work in `docs/design-system/README.md`.

## 4. What this does not do

- No screenshot comparison and no baseline images.
- No periodic audit run. The tests run on every change; findings of a one-off audit become tasks (`luismc-artifacts`, `scripts/plan_rows_check.py`).
