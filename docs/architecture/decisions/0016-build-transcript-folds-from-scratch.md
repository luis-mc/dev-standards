---
id: 0016-build-transcript-folds-from-scratch
title: Build transcript folds from scratch
status: accepted
date: 2026-10-13
supersedes:
superseded_by:
type: explanation
---
# Build transcript folds from scratch

## Context and problem

A third-party plugin folds diffs in the transcript. Adopting it means depending on code the owner does not control, and its chords clash with other bindings.

## Options considered

1. Adopt the third-party plugin. No work, but no control and a clash of chords.
2. Build our own, learning the idea only. Chosen.

## Decision

`luismc-transcript-folds` is written from the plugin API alone. None of the other plugin's code, names or layout is used, and its chords are different so both can be installed together. The owner uninstalls the other plugin once ours is live.

## Consequences

We own the code and can test it. The cost is writing four parts: folded diffs, folded commands, the session tally and compact mode. See the [transcript-folds spec](../../features/transcript-folds/spec.md).
