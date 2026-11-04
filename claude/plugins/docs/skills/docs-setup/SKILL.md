---
name: docs-setup
description: Lay out a repository's docs to the documentation standard (DOCSPEC), or move an existing repo to it. Use when the user wants to set up, standardise, restructure or migrate docs, move docs/specs or docs/guides into the new layout, create docs/overview, AGENTS.md or docs/docs.json, or move the artifacts record to docs/project. Dry run by default; moves with git mv, rewrites links, never deletes.
model: sonnet
effort: medium
---

# Docs — setup

Runs `scripts/docs_setup.py` from the `luismc-docs` plugin (DOCSPEC §9). The layout rules are in `references/docspec.md`. Read §2 and §9 first.

## How this setup talks to you (setup pattern)

This setup follows section 13 of `docs/features/delivery/shared-self-hosted-runners.md`.

1. **Plan first.** Before any change, show one plan: the folders and files it will create or move (with paths), that nothing is deleted, what lands outside the repository (nothing), what needs the owner (a yes, the app and topic names, the guesses to confirm) and about how long it takes (a minute for `init`, a few minutes for `migrate`). For an existing repo the plan is the `migrate` dry run. Ask for one yes.
2. **Do the heavy lifting.** After the yes, run every command yourself: `init` or `migrate --apply`, the `docs.json` edit (`apps`, `topics`), `docs_index.py build` and `docs_check.py`. Leave to the owner only what you cannot do: the guesses only they can judge, and the commit and push. Give each an exact step and check it afterwards.
3. **One line per step.** While it runs, print one line per step: what you are doing, then done, or failed with the reason and the fix.
4. **Finish with three parts.** **Done** (what changed, with paths). **Left for you** (numbered, exact steps). **What you can do now**: `/luismc-docs:docs-check` (check links and freshness), `/luismc-docs:docs-index` (build the offline site; open `docs/index.html`), `/luismc-docs:feature-spec-new` (write a feature spec), `/luismc-docs:docs-note` (add a change note for your task), `/luismc-docs:design-system-setup` (start the design system). Give each one line with an example.
5. **Safe to run again.** A second run says what is already set (the layout, `docs.json`) and changes only what is missing.

```bash
S="${CLAUDE_PLUGIN_ROOT}/scripts/docs_setup.py"
python3 "$S" init --apply --app web --topic library       # new repo: layout, docs.json, overview stubs, AGENTS.md
python3 "$S" migrate                                      # existing repo: print the plan, change nothing
python3 "$S" migrate --map docs/specs/x.md=docs/architecture/x.md   # override a guessed target
python3 "$S" migrate --apply                              # git mv, rewrite links, front matter stubs, layout
python3 "$S" move-record --apply                          # artifacts record to record_dir (docs/project)
```

## Steps for an existing repo

1. Confirm no branch is in flight (run between trains, R9.8).
2. Run `migrate` and read the plan. Lines marked `guess` come from the file name. The owner decides which guesses are wrong, and you pass `--map`.
3. Run `migrate --apply` on its own branch. Exit 2 means a target already existed. The file was kept; decide by hand.
4. Ask the owner for the app names and topics, write them into `docs/docs.json` yourself, then run `docs_index.py build` and `docs_check.py`.
5. Report the gaps list (`docs/features/index.md`, Gaps). Content gaps become tasks. This skill does not rewrite docs (R9.5).

`docs/work/` is never moved. If it holds files, say so in the report. Do not commit generated files by hand: `docs_index.py build` writes them.
