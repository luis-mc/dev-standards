---
id: 0070-claude-setup-all-plugins
title: claude-setup turns on and configures all plugins in the project
status: accepted
date: 2026-10-31
supersedes:
superseded_by:
type: explanation
---
# claude-setup turns on and configures all plugins in the project

## Context and problem

`/luismc-project-setup:claude-setup` turned on only luismc-artifacts and luismc-delivery in the project settings and luismc-transcript-folds at user level. It never installed a plugin. The other plugins were left to the owner.

## Options considered

Plugins to turn on:

1. The two it did before.
2. All plugins of the marketplace, read from `.claude-plugin/marketplace.json`. Chosen by the owner.

Install:

1. Turn on only and print the install commands.
2. Install each missing plugin with `claude plugin install <name>@<marketplace>` after the owner confirms in the summary, then tell the owner to reload plugins. Chosen.

Scope:

1. Project for workflow plugins, user for tools.
2. Everything at user level.
3. Everything in the project settings. Chosen. Only luismc-transcript-folds and its two chords stay at user level, as before.

Configuration (all three chosen):

1. luismc-docs: `docs_setup.py init --apply` in a repo without docs; in a repo with docs, show the `migrate` dry-run plan and never apply it without the owner.
2. luismc-artifacts: create the record with `record_dir` `docs/project` when absent (DOCSPEC R2.4).
3. luismc-delivery: write `.delivery/config.json` from the template when absent (caps 50/3/53, raised from 20/3/23 by the owner on 31 Oct; `ci.yml`); when present, raise caps that are lower and show `current -> new`.

## Decision

The options marked chosen. The skill reads the plugin list from the marketplace file, with the eight names as a fallback. `tools/test_claude_setup_plugins.py` fails when the settings template or the SKILL.md table misses a marketplace plugin.

Points the brief left open: the template lists luismc-transcript-folds too, so the project also enables it (the user-level entry and chords stay as they were). "The CI workflows" is `watcher.ci_workflows: ["ci.yml"]` in the template. Caps are only ever raised, never lowered.

## Consequences

A new project gets every plugin and a working first setup in one run. The run asks the owner to confirm more actions. An existing delivery config keeps all its other keys.
