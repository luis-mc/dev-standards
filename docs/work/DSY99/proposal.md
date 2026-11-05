# DSY99 proposal: design-system enforcement kit (draft for the owner)

Owner decision D203 (4 Nov). Local branch `DSY99-ds-enforcement-kit`. Nothing is pushed. No plugin `"version"` and no spec Version line or change log was touched. Everything is generic: no other project's name or path is in any file.

The kit lets a project that uses the `luismc-docs` design system make a breach fail a test, not only cite a rule. The tests read source text and the rendered DOM. There is no screenshot comparison.

## Files added or changed

### luismc-docs (parts 1, 2, 5)

| File | Change | Why |
|---|---|---|
| `claude/plugins/docs/templates/design-system/guards/typescript-vitest-kit/no-app-css-scan.ts` | new | Part 1. Scans app folders for stylesheets, CSS-in-JS, `style=` with layout or colour, classes the shared UI package does not define. `CONFIG` names the app folders and the shared UI folder. Includes the ratchet judge. |
| `.../no-app-css.test.ts`, `.../no-app-css.known.json` | new | Part 1. The ratchet test (new breach fails; fixed breach still listed fails) and its self-tests. The list starts empty; the project fills it at install with one removing task per entry. |
| `.../dom-layout.ts` | new | Part 2. Browser-side measurement at 360, 393 and 1300 px: no sideways overflow, gaps on the spacing scale, aligned left edges, stacked buttons of one width, primary action in view. Selectors and the spacing property prefix are options. Known-breach ratchet. |
| `.../dom-layout-judge.test.ts`, `.../dom-layout-example.spec.ts` | new | Self-test of the pure parts; an example Playwright spec to copy per app. |
| `.../wizard-behaviour.ts`, `.../wizard-behaviour.test.ts` | new | Part 2. The wizard harness pattern: a driver per wizard returns a snapshot per state; rules are later steps not pressable, exactly one primary, a disabled primary shows its reason, Stop (and Pause) when the job can, Done never empty, a button with an open request is disabled. `WIZARD_BEHAVIOUR_TO_FIX` is the shrinking table. The test file holds the self-tests that plant each breach. |
| `claude/plugins/docs/templates/ui-brief-checklist.md` | new | Part 5. Checklist for UI briefs and PR bodies: version and sections followed, wizard states rendered, shared parts named, no hand-made parts, kit green, no list entry added. It sits in `templates/`, not `templates/design-system/`, because `init` copies the latter into `docs/design-system/`. |
| `claude/plugins/docs/scripts/design_system.py` | edit (2 lines) | New guard stack `typescript-vitest-kit`; `guards --stack typescript-vitest-kit` copies the kit. The default stack is unchanged, so no existing project gets the kit by accident. |
| `claude/plugins/docs/skills/design-system-setup/SKILL.md` | edit | New "Enforcement kit" section, after the owner's yes. |

### luismc-delivery (parts 3, 4)

| File | Change | Why |
|---|---|---|
| `claude/plugins/delivery/references/design-gate.md` | new | Part 3. Where each kit test runs (branch gate `guards`, `unit`, `e2e` steps; pre-push; CI under any option), how to make it a required check (scope entry in `ci-scope.json`, job in `watcher.ci_workflows`, ruleset context set by the owner), and the ratchet rules a reviewer checks. |
| `claude/plugins/delivery/scripts/hook_design_edit.py` | new, not wired | Part 4. PostToolUse hook for Edit, MultiEdit and Write. Warns once when an edit adds CSS or a hand-made button, table, tab row or progress bar under the app paths. Active only where `docs/design-system/` exists. Warns only; always exits 0. Paths from `.delivery/config.json` `design_system.app_paths` and `shared_paths` (defaults `apps/` and `packages/ui/`). |

To wire it later, add to `hooks/hooks.json` under `PostToolUse`:

```json
{"matcher": "Edit|MultiEdit|Write", "hooks": [{"type": "command",
  "command": "if command -v python3 >/dev/null 2>&1; then python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/hook_design_edit.py\"; else python \"${CLAUDE_PLUGIN_ROOT}/scripts/hook_design_edit.py\"; fi",
  "timeout": 10}]}
```

It is left unwired because the existing PostToolUse entry has a different matcher and a hook change affects every project with the plugin. A test (`the_hook_is_a_draft_and_not_wired`) pins this until the owner decides.

### luismc-artifacts (part 6)

| File | Change | Why |
|---|---|---|
| `claude/plugins/artifacts/scripts/plan_rows_check.py` | new | Reads a report and the task registry. Finds numbered table rows, numbered list items and ID rows (`B07`); skips sections such as "Not proposed". A row is tasked when a task's item or detail holds its key `<tag>#<id>`. Lists the rows without a task, with `--commands` a `task-add` line for each. It writes nothing. Exit 1 when rows are missing. |
| `claude/plugins/artifacts/skills/task-add/SKILL.md` | edit | New section "Plan rows and audit findings": after such a report, run the check and add one task per listed row in the same turn, with the key in the detail. No periodic audit. |

### Repo files

| File | Why |
|---|---|
| `tools/test_ds_enforcement.py` | 13 tests for all of the above (below). `python -I tools/test_ds_enforcement.py`. |
| `tools/fixtures/vitest_shim/{vitest.mjs,hooks.mjs,run.mjs}` | A 60-line stand-in for `vitest` so the shipped TypeScript tests run with plain Node 22.6 or later; no install, no network. Skipped by the test when Node is old or missing. |
| `docs/architecture/changes/DSY99-ds-enforcement-kit-{docs,delivery,artifacts}.md` | Plugin change notes. |
| `docs/features/{docs,delivery,artifacts}/changes/DSY99.md` | Feature-spec change notes (made with `docs_fold.py note`). |
| `docs/work/DSY99-report.md`, `docs/work/DSY99/proposal.md` | Report and this proposal; `docs_work.py strip` removes them before a join. |

## Open questions for the owner

1. **Hook wiring.** Wire `hook_design_edit.py` into `hooks.json` now, or keep it a draft? Warn only, or deny (PreToolUse) after the first warning in a turn?
2. **Config key.** `design_system.app_paths` and `shared_paths` in `.delivery/config.json` are not in `config-schema.json` (unknown keys only warn). Add them to the schema, or read the paths from a kit file in `scripts/design/` instead?
3. **Spec text.** The kit has no requirement ID. Add a short requirement in DOCSPEC section 15 (enforcement kit is optional, ratchet lists only shrink) and one DELIVERYSPEC line for the required check? The spec files were not touched here.
4. **Install default.** Should `design-system-setup` offer the kit in its plan by default for any project that has numbered versions, or only on request?
5. **Ratchet growth check.** Should `change_notes.py` (or a new guard) fail a diff that adds or raises a known-list entry outside the install change? It is described in `design-gate.md` as a review rule only.
6. **Stacks.** Only the TypeScript and Vitest stack is drafted (as for the existing guard templates). The wizard harness needs a component test runner per project. Which other stacks are wanted?
7. **Wizard states.** The state list (first run, planning, ready to review, running, paused, stopped, failed, done, done after reload) is generic. Confirm it, or let a project list its own.
8. **Plan-to-tasks trigger.** Run `plan_rows_check.py` only when asked (skill text), or also from the Stop hook of the artifacts plugin for any report written in the turn? The Stop hook would block the end of a turn while rows are untasked. The task key convention (`<tag>#<id>` in the detail) needs the owner's yes.
9. **Brief checklist home.** Paste it into `AGENTS.md` and the PR template by hand, or have a setup command do it?
10. **Docs check.** `docs_check.py` reports M1 (warning) for `references/design-gate.md`: no spec maps that code root. Map it in the delivery spec's `code:` list when the spec is next edited.
