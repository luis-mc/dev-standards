# DL263 report

Base check: template had `ref: {{DEV_STANDARDS_REF}}` and the by-hand comment. OK.

## What changed
- New `claude-setup/assets/ci_pin.py`: status line, `--check` (exit 1 when stale), `--bump` (rewrites only the `ref:` value, keeps line endings and the trailing comment, never commits).
- The marketplace checkout comes from `known_marketplaces.json`. Expected ref: tag `v<ver>` if one exists, else the checkout HEAD. A pin is stale when it is not that commit and not a descendant.
- Template comment now says the pin must match the installed plugins and names `ci_pin.py --bump`.
- SKILL.md: status scan line and one sentence in the CI step.
- Project-setup spec text, feature note `docs/features/project-setup/changes/DL263.md`, change note `docs/architecture/changes/DL263-ci-pin-bump.md`.
- Tests: `tools/test_dl263_ci_pin.py` (9 cases), registered as `project-setup-dl263` in `.claude/suites.json`.

## Tests
- `python3 tools/test_dl263_ci_pin.py`: 9 OK (first run caught a CRLF bug in bump, fixed).
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 on docs/work (expected) and M1 for the new test file.
- spec-lint dispatched on this branch, `areas=specs`, run 43118080116: all jobs passed or skipped except `docs check`, which failed only on the expected W1.

## Follow-ups
- Not found: no existing status/apply script, so the new script stands alone and SKILL.md calls it.
- M1 warning: map `tools/test_dl263_ci_pin.py` in a spec's `code:` (not my file to edit).
- No release tags exist in the repo, so the HEAD fallback is what runs today.
- The status line prints `python3 ci_pin.py --bump`; the full path depends on the install.
- Strip `docs/work/` before the join (D9).

Branch head SHA: see `git rev-parse DL263-ci-pin-bump` (the code commit is aa5206f).

READY
