# Change notes

A branch never edits a spec's `**Version:**` line or change log, or a plugin's `"version"`; it adds a note here instead, so parallel branches do not conflict.

A note is `docs/architecture/changes/<task-id>-<slug>.md`, front matter `spec:` (and/or `plugin:` with the path of its `plugin.json`) and `change: patch|minor|major`, then one or two sentences for the change log.

Settings: `tools/change-notes.json` (`notes_dir` names this folder; DS109 moved it from `docs/specs/changes/`). Tool: `claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery/change_notes.py` (CONTRACT.md "U7"); spec-lint runs its `check --config tools/change-notes.json` on every pull request, and `main` and any `*-integration` branch are exempt.

Work is done on `main` (owner, 30 Oct); the orchestrator folds there: `change_notes.py fold --config tools/change-notes.json` (`--dry-run` first) bumps each target by the highest kind among its notes, writes one entry under the spec's change-log heading, and deletes the notes. Do not fold by hand.

AUTHSPEC has no change log, so a fold only bumps its version; ARTIFACTSPEC and STACKSPEC get an entry right under `0.4 What changed` and `0.1 What changed`.

Guards (DS102): a pull request that changes a plugin's files (not its `tests/`) needs a note naming that plugin's `plugin.json` (`plugin_notes_required` in `tools/change-notes.json`), and spec-lint on every push to `main` runs `change_notes.py pending`, which fails while a note waits to be folded.
