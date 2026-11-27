# Agent rules

Standing rules for every agent working in this repository. `CLAUDE.md` imports this file.

## Roles

- A **task agent** does one task on its own branch.
- The **orchestrator** is the main session. It launches task agents and joins their branches.
- The **watcher** is the delivery plugin's watcher script. It pushes trains and merges.

## Working in this repository

- Work on a task branch `<task-id>-<slug>`. Push only that branch. Never push to `main`.
- A task agent opens draft pull requests only. The orchestrator or the watcher opens the one ready pull request, from the integration branch (DELIVERYSPEC DL-08).
- Merges follow `watcher.merge_mode` in `.delivery/config.json` (DL-03). In `auto` (the default) the watcher merges a green pull request. In `manual` the owner merges it by hand. No agent session merges: only the watcher does. Agents never run `gh pr merge`.
- Hooks and the docs plugin never commit, push or merge. They write files in the working tree. The delivery watcher pushes and merges per `merge_mode`.
- Never edit a `**Version:**` line, a change log or a plugin's `"version"`. Add a change note instead (DOCSPEC R7.1). A feature spec gets its note from `docs_fold.py` (see below). A shipped spec or a plugin gets its note in `docs/architecture/changes/`. A change to a plugin's files needs a note that names its `plugin.json`.
- The release fold runs on `main` after the merge. It writes the versions and change logs.
- Requirement IDs, section numbers and `**Version:**` lines never move or renumber. Projects, hooks and tests cite them.
- Name no other project in any file or commit message. Only dev-standards and its plugins.
- Write plain, short English: one idea per sentence, no marketing words.

## Tests

- Test only what you touch. `python tools/ci_areas.py --branch-advice` says `light` or `heavy` (DL-12).
- Light: run the touched suites locally.
- Heavy: run a short local smoke of what you changed. Then run branch CI for your own area with the one command the advice prints: `gh workflow run spec-lint.yml --ref <branch> -f areas=<areas>`.
- Run no mutation passes and no Docker unless the task says so. See `docs/guides/testing.md`.

## Documentation (DOCSPEC)

- Read `docs/README.md` first. The docs live in `docs/`, laid out by reader question.
- A change to behaviour updates its feature spec in the same branch and adds a note: `python3 <luismc-docs>/scripts/docs_fold.py note --doc features/<feature> --task <TASK> --change <patch|minor|major> --text "..."`.
- A change that needs no doc says so in a commit message: `Docs: none, <reason>`.
- UX rules live only in `docs/design-system/`. A feature spec shows its screens and cites rules by ID.
- Agent briefs and reports live in `docs/work/` on your branch only. Never add them to a pull request for the default branch.
- Do not edit generated files: `docs/index.html`, `docs/llms.txt`, `docs/features/index.md`, `docs/architecture/decisions.md`, `docs/docs-map.json` and `docs/reference/`.
- Before you finish: `python3 <luismc-docs>/scripts/docs_check.py`.
