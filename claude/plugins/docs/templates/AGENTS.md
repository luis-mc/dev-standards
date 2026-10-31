# Agent rules

Standing rules for every agent working in this repository. `CLAUDE.md` imports this file.

## Documentation (DOCSPEC)

- The docs live in `docs/`, laid out by reader question: `overview/`, `features/`, `design-system/`, `architecture/`, `guides/`, `reference/`, `project/`. Read `docs/README.md` first.
- A task that changes behaviour updates the feature spec in the same branch and adds a change note: `python3 <luismc-docs>/scripts/docs_fold.py note --doc features/<feature> --task <TASK> --change minor --text "..."`. Never edit a version table by hand; the release fold writes it.
- A change that needs no doc says so in a commit message: `Docs: none, <reason>`.
- UX rules live only in `docs/design-system/`. A feature spec shows its screens and cites rules by ID.
- Agent briefs and reports live in `docs/work/` on your branch only. Never add them to a pull request for the default branch.
- Do not edit generated files (`docs/index.html`, `docs/llms.txt`, `docs/features/index.md`, `docs/architecture/decisions.md`, `docs/docs-map.json`, `docs/reference/`).
- Before you finish: `python3 <luismc-docs>/scripts/docs_check.py`.
