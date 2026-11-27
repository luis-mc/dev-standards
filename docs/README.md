# Documentation

How the docs of this repository are kept. The rules are in DOCSPEC (`claude/plugins/docs/references/docspec.md`, shipped by the `luismc-docs` plugin). The settings are in `docs.json`.

Open `index.html` in a browser (double-click, no server). If it is out of date, run `python3 claude/plugins/docs/scripts/docs_index.py build`.

Start with the [overview](overview/README.md).

| Folder | The reader's question |
|---|---|
| `overview/` | What is this, who is it for, how do the parts fit? |
| `features/` | What does feature X do, and how is it built? One folder per feature. |
| `design-system/` | What are the UX rules, tokens, components? The only home of UX rules. Not present here: this repository has no UI. |
| `architecture/` | How is the system built, and why? Binding cross-cutting specs, decision records and change notes. |
| `guides/` | How do I do task Y (set up, release, restore)? |
| `reference/` | What exactly is the value (API, CLI, config keys)? Generated. |
| `project/` | The artifacts record: progress and decisions in flight. |

## Guides

- [Testing in dev-standards](guides/testing.md)
- [Set up CI for a project](guides/set-up-ci.md)
- [Set up the CI fallback and try it on a test repository](guides/ci-fallback-test-run.md)
- [Shared CI on your machine](guides/shared-self-hosted-runners.md)
- [Run work in cloud routines](guides/cloud-routines.md)
- [What the setup skills do and what you can do after](guides/setup-skills.md)
- [Adopt the lifecycle kit in a project](guides/lifecycle-adoption.md)
- [Rust beside a JS stack](guides/rust-beside-js.md)
- [VM checks on a kvm runner](guides/vm-checks.md)
- [Windows packaging on the Linux pool](guides/windows-packaging.md)
- [Fix a citation of a removed delivery rule](guides/removed-delivery-ids.md)

## Settings

`docs.json` holds the app names (`apps`), the topics, the record folder, the default branch (`main`), the days before a doc counts as stale and the code folders the checks map (`code_roots`). The app names in [the apps page](overview/apps.md) are exactly its `apps` values.

## Change notes

A branch never edits a spec's `**Version:**` line or a plugin's `version`. It adds a change note instead. A feature spec's note goes in `features/<feature>/changes/` (`docs_fold.py note`). A shipped spec's or a plugin's note goes in `architecture/changes/`; see that folder's `README.md`. The release fold runs on `main` after the merge. It turns the notes into versions and change-log entries, then deletes them. Do not fold by hand.

A change that needs no doc puts `Docs: none, <reason>` in a commit message.

## Replaced docs

A replaced doc is deleted, not archived. This repository has no `archive/` folder. Git history keeps the old text.

## Generated files

`index.html`, `llms.txt`, `features/index.md`, `architecture/decisions.md`, `docs-map.json` and `reference/` are written by the scripts. Do not edit them by hand. A task branch does not commit them; the release regenerates them.

## Agent work files

`work/` holds agent briefs and reports. It exists only on agent branches and never reaches `main`. Standing rules live in the root `AGENTS.md`.

## Check

Before you finish: `python3 claude/plugins/docs/scripts/docs_check.py`.
