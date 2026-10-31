---
id: 0050-upgrade-notes-are-guides
title: Upgrade notes are how-to guides, the originals are archived
status: accepted
date: 2026-11-01
supersedes:
superseded_by:
type: explanation
---
# Upgrade notes are how-to guides, the originals are archived

## Context and problem

The STACKSPEC 8.0.0 upgrade note sat in `docs/upgrades/`, a folder DOCSPEC does not define. It is a task a person performs, so DOCSPEC section 2 (R2.2) puts it in `guides/`. ADR 0001 already sends upgrade notes to feature specs, MADRs or the archive.

## Options considered

1. Keep `docs/upgrades/` as a folder. Easy, but it is outside the layout and the pages are not tagged with a type.
2. Fold the note into the project-setup feature spec. The spec says how the plugin works now, not how to move a project, so the steps would not fit.
3. Write a how-to guide in `docs/guides/` and move the original to `docs/archive/upgrades/` with a pointer. Chosen.

## Decision

An upgrade note becomes a how-to guide in `docs/guides/`, named `upgrade-<spec>-<major>.md`. The original moves with `git mv` to `docs/archive/upgrades/` and starts with a line that points to the guide. The archive copy is history only and is never cited as a rule.

## Consequences

Upgrade steps sit with the other guides, carry a Diataxis type and are indexed. The prompt text is kept word for word, so a project that already pasted it sees no change. Guides are not versioned, so git is their history.
