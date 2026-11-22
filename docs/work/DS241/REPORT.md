# DS241 report

## Files
- `claude/plugins/docs/scripts/design_system.py`: `verify` command (DS7 approval record, DS8 implementation approval, DS9 gallery stamp), `approve-implementation --as-live`.
- `claude/plugins/docs/templates/design-system/guards/typescript-vitest/`: `design-system.ts` (`sourcesDigest`, `approvalProblems`), `design-system-freeze.test.ts` (no more silent skip), new `design-system-gallery.test.ts`.
- `claude/plugins/docs/templates/design-system/README.md`: order of work and approval rules.
- `claude/plugins/docs/references/docspec.md`: new R15.14 and its proof row. (R15.13 was taken by the lifecycle file, so the new ID is R15.14.)
- `docs/features/docs/spec.md` (R5.24), notes `docs/architecture/changes/DS241-ds-approval-guards.md`, `docs/features/docs/changes/DS241.md`.
- Tests: `claude/plugins/docs/tests/test_design_system.py`, `tools/test_ds_guard_templates.py`.

## Decisions
- Only the TypeScript and Vitest stack has a freeze guard template; no other stack has a copy to change. The Python `verify` command is the stack-neutral path.
- Gallery hook: the stamp convention (`<!-- source-digest: X -->`) or `design_gallery_digest_command` in `docs.json` (guard test: env `DESIGN_GALLERY_DIGEST_CMD`).
- Release context: branch name starting `release`, the default branch, `--release`, or `DESIGN_GATE=release` (set it on the ready PR job).

## Tests
- `python3 -m unittest discover -s claude/plugins/docs/tests -p test_design_system.py`: 45 OK (new: pass/fail fixtures per guard, `--as-live`, task branch warns, release branch fails, own-generator hook).
- `python3 -I tools/test_ds_enforcement.py`: 33 passed, 0 failed.
- Template guards run by real vitest on a scratch fixture: fails without implementation approval, passes after `--as-live`, stale gallery warns on a task branch and fails with `DESIGN_GATE=release`. Passed by hand.
- `tools/test_ds_guard_templates.py` is edited with matching cases (implementation, incomplete record, stale gallery on task and release branch) but NOT run: the session guard refuses this heavy suite locally and Actions are off limits. Needs a CI run.

## docs_check
Only two findings remain: W1 (this work folder, expected on a branch) and M1 on `features/lifecycle` (covered by the commit message `Docs: none`). One warning: `tools/test_ds_guard_templates.py` is not mapped by any doc.

## Questions for the owner
- Should the default branch count as a release context for DS9 (now yes)?
- Existing projects fail DS8 at once until they run `approve-implementation --as-live`; this follows the "block at once" rule.

NOT READY: tools/test_ds_guard_templates.py edits not run (heavy suite, needs CI)
