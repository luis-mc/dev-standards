# Agent rules

Standing rules for every agent working in this repository. `CLAUDE.md` imports this file.

## Working in this repository

- Work happens on `main`. An agent works on a short-lived task branch named `<task-id>-<slug>`, pushes only that branch, and never pushes to `main`, merges, or opens a ready pull request.
- A branch never edits a spec's `**Version:**` line, its change log, or a plugin's `"version"`. It adds a change note in `docs/architecture/changes/`; the release fold writes versions. A change to a plugin's files needs a note naming that plugin's `plugin.json`.
- Requirement IDs, section numbers and `**Version:**` lines in the shipped specs stay where they are. Projects, hooks and tests cite them.
- Plugins write files in the working tree. They never commit, push or merge.
- Name no other project in any file or commit message. Only dev-standards and its plugins.
- Keep tests light: `python tools/ci_areas.py --branch-advice` says what to run. Run no mutation passes and no Docker unless the task says so. See `docs/testing.md`.
- Write plain, short English: one idea per sentence, no marketing words.

## Documentation (DOCSPEC)

- The docs live in `docs/`, laid out by reader question: `overview/`, `features/`, `design-system/`, `architecture/`, `guides/`, `reference/`, `project/`. Read `docs/README.md` first.
- A task that changes behaviour updates the feature spec in the same branch and adds a change note: `python3 <luismc-docs>/scripts/docs_fold.py note --doc features/<feature> --task <TASK> --change minor --text "..."`. Never edit a version table by hand; the release fold writes it.
- A change that needs no doc says so in a commit message: `Docs: none, <reason>`.
- UX rules live only in `docs/design-system/`. A feature spec shows its screens and cites rules by ID.
- Agent briefs and reports live in `docs/work/` on your branch only. Never add them to a pull request for the default branch.
- Do not edit generated files (`docs/index.html`, `docs/llms.txt`, `docs/features/index.md`, `docs/architecture/decisions.md`, `docs/docs-map.json`, `docs/reference/`).
- Before you finish: `python3 <luismc-docs>/scripts/docs_check.py`.
