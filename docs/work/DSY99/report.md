# DSY99 report

## Owner answers 5 Nov

Status: all ten answers applied and committed locally on DSY99-ds-enforcement-kit. Nothing pushed or published.

- D231 done. `hook_design_edit.py` is wired in the delivery `hooks.json` (PreToolUse `Edit|MultiEdit|Write`). The first breach in a turn is allowed with a warning, a repeat in the same turn is denied. A turn ends at UserPromptSubmit or Stop (both call the script to clear a per-session count in the temp folder).
- D232 done. `design_system.app_paths` and `shared_paths` are typed and documented in `config-schema.json`; design-system-setup asks for them and writes them to `.delivery/config.json`.
- D233 done. DOCSPEC R15.9 and DELIVERYSPEC DL-92, each with a change note (`DSY99-docspec.md`, `DSY99-deliveryspec.md`); no Version line touched.
- D234 done. The setup plan includes the kit by default for a project with a numbered version; the owner may decline.
- D235 done. `change_notes.py check` (delivery template) fails a branch diff that adds an entry to or raises a count in a known list that exists at the base (`known_lists`, default `scripts/design/*.known.json`); a list new at the base is the install change. Tests in `tools/test_ds_enforcement.py`.
- D243 done. Kit `README.md` says TypeScript with Vitest only; the SKILL says to leave the kit out on other stacks.
- D237 done. `wizard-behaviour.ts`: the nine states always run; a driver `states` list may add states; `droppedStates` makes `judgeAll` fail a driver that lists fewer. TS self-tests added (run under the Node shim).
- D238 done. `hook_end_of_turn.py` (Stop) runs the plan-rows check for report-like files under `docs/work/` changed in the last 2 hours and not yet found clean; it blocks with `task-add` lines. Key `<tag>#<id>` documented in the task-add skill.
- D239 done. `design_system.py brief [--apply]` writes and refreshes the checklist as a marked block in `AGENTS.md` and `.github/pull_request_template.md`; idempotent.
- D240 done. `references/design-gate.md` is in the `code:` list of `docs/features/delivery/spec.md`.

Follow-ups:

- DSY99-F1: `KNOWN_LAYOUT_BREACHES` and `WIZARD_BEHAVIOUR_TO_FIX` are TypeScript constants, so the D235 guard covers only the JSON list (`no-app-css.known.json`). Move them to JSON lists to cover all three.
- DSY99-F2: the Stop-hook "written in the turn" test is approximate (file changed in the last 2 hours and not already found clean in this session), because a Stop hook has no turn start time.
- DSY99-F3: `docs_check.py` still shows W1 (this report and the proposal under docs/work/; run `docs_work.py strip` before a join) and an M1 warning for `tools/fixtures/vitest_shim/hooks.mjs` (map it in a spec `code:` list when convenient).
- DSY99-F4: `tools/test_delivery_hooks.py` has failures that also fail on the unchanged branch head (22 there, 4 here in this run; D4, DL-36/37, DL-38 caps among them); not caused by this work, depends on the machine.

Tests: `python -I tools/test_ds_enforcement.py` 25 passed, 0 failed. `tools/test_rule_tags.py` passed. `docs_check.py`: only W1 as above. `spec_check` on docspec and DELIVERYSPEC: 0 errors.

CODE DONE

## D244 loading state

Status: done, committed locally on DSY99-ds-enforcement-kit. Nothing pushed or published.

- `wizard-behaviour.ts`: `WIZARD_STATES` now has ten states, `loading` first (D237 + D244); doc comment, `states` comment, `droppedStates` and `judgeAll` comments say ten. `droppedStates` still fails a driver that omits any required state (now 8 dropped for a two-state list).
- New judge in `checkWizard` for state `loading`: rules `loading-action-hidden` (no primary shown), `loading-action-live` (any non-Back button pressable), `loading-wait-not-once` (`waitLines` must be 1), `loading-back-missing` (Back, role `back`, present and free), `loading-done-shown` (no Done text). The existing disabled-primary-reason rule still applies. Snapshot gained `waitLines?`; button role gained `back`.
- Self-tests: new `loading state (D244)` block (passes locked primary + Back free; fails live primary; fails hidden primary; fails locked Back, wait twice, Done text); the ten-state tests updated (counts 8 dropped, 11 with an added state, 10 default).
- Docs: kit README, design-system-setup SKILL, DOCSPEC R15.9 text, DSY99 change notes (docspec, kit-docs, feature note) now say ten states. `references/design-gate.md` does not list the states: unchanged. No version headers touched.
- `tools/test_ds_enforcement.py`: the source check now expects ten states including `loading`.

Tests: `python -I tools/test_ds_enforcement.py` 25 passed, 0 failed (includes the TS self-tests under the Node shim: 20 passed, 0 failed). `docs_check.py`: only the known W1 error (docs/work files) and warnings as before. `spec_check` on docspec.md: see commit run.

CODE DONE
