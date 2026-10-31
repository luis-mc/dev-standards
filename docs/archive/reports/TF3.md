# TF3 and DS65: claude-setup installs transcript-folds, marketplace renamed

Branch `TF3-claude-setup-install` (from `DS64-integration`). Contract: `docs/plans/transcript-folds.md`.

## Changes
DS65 (own commit):
- `.claude-plugin/marketplace.json`: name `dev-standards`, `(luismc-dev-tools)` dropped from the description, entry `luismc-transcript-folds` added (plugins kept sorted by name).
- `README.md`: intro and every install line use `@dev-standards`; one sentence for a machine that registered another name; install line and a section for luismc-transcript-folds (chords, slash commands, three settings); claude-setup bullet for the new user-level pieces.
- `tools/test_model_profiles.py`: hard-coded marketplace mutation uses `dev-standards`.

TF3:
- `SKILL.md`: description and intro name the standard user-level pieces; settings key table row; "enabledPlugins writes one entry per file" text updated (no longer "none to a user target"); new step 2 section "The transcript-folds pieces" (enabledPlugins entry, keybindings merge rules, conflicts, JSON validity, install note); step 3 lists both pieces and chord conflicts; step 4 verifies both; step 5 reports them and the install and `/reload-plugins` notes.
- New asset `assets/keybindings.json` (Global context, `ctrl+x d` -> `theme:toggleSyntaxHighlighting`, `ctrl+x f` -> `theme:editCustom`).
- `tools/test_model_profiles.py`: checks K1 (asset exact; plugin source names both actions when `claude/plugins/transcript-folds/hooks/` exists, otherwise skipped with a printed message) and K2 (SKILL.md text), each proved able to fail by 5 mutations.
- Change note `docs/specs/changes/TF3-claude-setup-install.md` (minor).

## Tests (local)
- `python tools/test_model_profiles.py`: OK, 0 failing; plugin-source cross-check SKIPPED with message (folder absent on this branch). Run via `run_suite.py --measure` because session_guard refuses a direct full run of an unmeasured suite.
- `tools/test_rule_tags.py`: passed (45 rule lines tagged). `tools/test_ci_areas.py`: all checks passed.
- change_notes check against `origin/DS64-integration`: ok.

## Open
- Leftover `luismc-dev-tools` outside my files: only `docs/plans/transcript-folds.md` (describes the rename; orchestrator's) and `docs/artifacts/` (not touched).
- After the join, rerun `python tools/test_model_profiles.py` so the K1 cross-check actually runs against the plugin source.
