# Change notes

A branch never edits a spec's `**Version:**` line or change log, or a plugin's `"version"`; it adds a note here instead, so parallel branches do not conflict.

A note is `docs/specs/changes/<task-id>-<slug>.md`, front matter `spec:` (and/or `plugin:` with the path of its `plugin.json`) and `change: patch|minor|major`, then one or two sentences for the change log.

Settings: `tools/change-notes.json`. Tool: `claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery/change_notes.py` (CONTRACT.md "U7"); spec-lint runs its `check --config tools/change-notes.json` on every pull request, and any `*-integration` branch is exempt.

The orchestrator folds on the integration branch before the ready PR: `change_notes.py fold --config tools/change-notes.json` (`--dry-run` first) bumps each target by the highest kind among its notes, writes one entry under the spec's change-log heading, and deletes the notes. Do not fold by hand.

AUTHSPEC has no change log, so a fold only bumps its version; ARTIFACTSPEC and STACKSPEC get an entry right under `0.4 What changed` and `0.1 What changed`.
