---
name: design-system-setup
description: Create and keep a project's design system under docs/design-system to DOCSPEC section 15 - README with the order of work, a next-version draft (ux-rules with rule IDs, components, tokens, content words, CHANGES, an offline review-visuals gallery), numbered read-only versions promoted only with a recorded owner approval, and guard-test templates per stack. Use when the user wants to set up, start, version, approve or promote a design system, add UX rules or tokens, build the review gallery, or add the design-system guard tests.
model: sonnet
effort: medium
---

# Design system - setup and keep

Runs `scripts/design_system.py` from the `luismc-docs` plugin (DOCSPEC section 15). Every command is a dry run until `--apply`.

## How this setup talks to you (setup pattern)

This setup follows section 13 of `docs/features/delivery/shared-self-hosted-runners.md`.

1. **Plan first.** Run `status` and `styles`, then show one plan: the folders and files `init` will create under `docs/design-system/` and `scripts/design/` (with paths), the starter tokens it may replace with the project's own values, the test runner file it will edit to include the guard tests, that nothing is written outside the repository, for a project with a numbered version (`v1` or later) the enforcement kit (below), included by default, with the owner's choice to decline it; the app and shared UI folders you will write to `.delivery/config.json` (`design_system.app_paths`, `design_system.shared_paths`), asked in the same plan; the marked checklist block `brief` will write into `AGENTS.md` and `.github/pull_request_template.md`; what needs the owner (a yes, the choice to use the found style values, the approval of a version) and about how long it takes (a few minutes). Ask for one yes.
2. **Do the heavy lifting.** After the yes, run these yourself: `init --apply`, `guards --apply`, the `CONFIG` edit at the top of `design-system-follow.test.ts` (source roots, extensions, token files, taken from the `styles` output), the edit that makes the test runner include `scripts/design/*.test.ts`, `visuals`, `check`, `brief --apply` (idempotent: it writes the checklist as a marked block and refreshes it on a rerun) and, when the kit is in the plan, the kit steps below. Leave to the owner only what you cannot do: approving a version (`promote`, `approve-implementation`), which needs their date and evidence, and the commit and push. Give each an exact step and check it afterwards.
3. **One line per step.** While it runs, print one line per step: what you are doing, then done, or failed with the reason and the fix.
4. **Finish with three parts.** **Done** (what changed, with paths). **Left for you** (numbered, exact steps: how to open `next-version/review-visuals/index.html`, what to look at, the `promote` command with the approval words). **What you can do now**: `design_system.py status` (see versions and approvals), `design_system.py visuals` (rebuild the gallery after a token change), `design_system.py check` (run the DS1-DS5 findings), the guard tests (run them with the project's test runner), and `promote` once the owner approves. Give each one line with an example.
5. **Safe to run again.** A second run says what exists (`init` never overwrites) and changes only what is missing.

```bash
S="${CLAUDE_PLUGIN_ROOT}/scripts/design_system.py"
python3 "$S" init --apply                  # docs/design-system/: README, approvals.json, next-version/ (never overwrites)
python3 "$S" styles                        # read-only: style files and CSS custom properties the project already has
python3 "$S" guards --apply                # guard tests into scripts/design/ (--stack typescript-vitest, --dest DIR)
python3 "$S" visuals                       # rebuild next-version/review-visuals/index.html: offline gallery with drawn swatches, contrast and every component (the session-start and stop hooks now do this when it is stale; running it by hand still works)
python3 "$S" check                         # DS1-DS5 findings (DS4 also flags a gallery from an older script); docs_check.py runs the same
python3 "$S" brief --apply                 # UI brief checklist as a marked block in AGENTS.md and .github/pull_request_template.md; rerun refreshes it
python3 "$S" status                        # versions, the enforced one, approvals
python3 "$S" promote --approved-by owner --approved-on 2026-11-02 --evidence "chat, 2026-11-02"   # dry run; add --apply
python3 "$S" approve-implementation v1 --approved-on 2026-11-20 --evidence "chat" --apply
```

## Style reading (after init): show, ask, then fill

`init` writes a project-neutral starter (every item is a starter item to keep, change or delete before v1 is approved). Then read the project's own styles:

1. Run `design_system.py styles`. It lists design-token files, theme and Tailwind configuration, and CSS custom properties. It changes nothing.
2. Show the owner the files and values found. Ask once: "Use these values in the starter tokens?"
3. Only on yes: replace the matching token values in `next-version/tokens.md` (colours, fonts, spacing, radius). Keep the token names. Check WCAG 2.2 AA contrast of the new pairs. Add a `CHANGES.md` entry and rebuild the gallery.
4. On no, or when nothing is found: keep the starter values.

## Rules to follow

- Every design change, even a typo, goes into `next-version/`; write a `CHANGES.md` entry (`- C<n>: ...`) and rebuild the gallery.
- Never edit a numbered folder (`v1`, `v2` ...): it is read-only after approval and its digest is in `approvals.json`.
- Only the owner approves. Never run `promote` or `approve-implementation` on your own judgment: you need the owner's approval date and where it was given (the chat, a comment) and you pass them as `--approved-on` and `--evidence`. Show the gallery to the owner first. It draws colour swatches with WCAG contrast, type, spacing and radius samples, and every component, light and dark side by side. Read its "Token gaps", "Contrast failures" and "Not drawn" lists before you show it. Rebuild `next-version` only; a numbered version is never rebuilt.
- Apps follow the highest numbered version. UI work for a new version waits for the owner's approval of the version, an audit of the apps, and the owner's approval of the implementation.
- Rules carry IDs (`UX-<n>`); feature specs and code cite the ID and never copy the rule. Words users see live in `content.md` (DOCSPEC R11.3).
- Templates hold structure and a starter set of generic, project-neutral rules. Keep, change or delete each one; never import another project's rules.

## Guard tests

`guards` copies `design-system.ts` (finds the enforced version, computes the digest) and three tests: layout, freeze (digest and branch diff against `DESIGN_BASE`, default `origin/main`) and follow (retired words, rule table and citations, raw colours). Edit `CONFIG` at the top of `design-system-follow.test.ts` yourself (source roots, extensions, token files), and make the test runner include `scripts/design/*.test.ts`, after the owner's yes to the plan. Other stacks: port the same three checks; the digest algorithm is in R15.5.

## Enforcement kit (offered by default for a project with a numbered version; the owner may decline)

**Stack: TypeScript and Vitest only for now.** There are no templates for other stacks. For a project on another stack, say so in the plan and leave the kit out.

For a project whose apps must follow the design system, not only cite it. `guards --stack typescript-vitest-kit --apply` copies three guards into `scripts/design/`. Each has a self-test and a ratchet list: a new breach fails, and a listed breach that is gone but still listed fails, so the list only shrinks. No screenshot comparison anywhere.

1. **No app CSS** (`no-app-css-scan.ts`, `no-app-css.test.ts`, `no-app-css.known.json`): app folders carry no stylesheet, no CSS-in-JS, no `style=` with layout or colour, no class the shared UI package does not define. Edit `CONFIG` (app folders, the shared UI folder) and `TASK_ID`. First run: put today's breaches in the known list, each with the task that removes it.
2. **DOM layout** (`dom-layout.ts`, `dom-layout-judge.test.ts`, `dom-layout-example.spec.ts`): at 360, 393 and 1300 px, no sideways overflow, gaps on the spacing scale, aligned left edges, stacked buttons of one width, the primary action in view. Copy the example spec per app and list its screens; known breaches go in `KNOWN_LAYOUT_BREACHES`.
3. **Wizard behaviour** (`wizard-behaviour.ts`, `wizard-behaviour.test.ts`): one driver per wizard renders it in each state and reads a snapshot from the DOM. The rules: later steps not pressable, exactly one primary, a disabled primary shows its reason, Stop when the job can stop, Done never empty, a button with an open request is disabled. The nine states are required: first run, planning, ready to review, running, paused, stopped, failed, done, done after reload. A driver may add states and never drops one; the harness fails a driver that lists fewer. Breaches go in `WIZARD_BEHAVIOUR_TO_FIX`, which only shrinks.

Then:

- Ask for the app folders and the shared UI folder, and write them to `.delivery/config.json` as `design_system.app_paths` and `design_system.shared_paths` (typed in the delivery plugin's `config-schema.json`; the edit-time hook `hook_design_edit.py` and the no-app-CSS `CONFIG` use the same values).
- Make the project's test runner include the three, and make them a required check (the delivery plugin's `references/design-gate.md`, DELIVERYSPEC DL-92).
- Run `brief --apply`: the UI brief and pull request checklist (`templates/ui-brief-checklist.md`) is written into `AGENTS.md` and the PR template, and refreshed when it changes.
- The known lists get entries only in this install change. After it, a diff that adds or raises one fails `change_notes.py check`.

Never import another project's known lists.

## Existing design system elsewhere

Move it to `docs/design-system/` with `git mv`, rewrite links and guard paths in one task (R15.8), add the earlier approvals to `approvals.json` by hand, then run `check`.
