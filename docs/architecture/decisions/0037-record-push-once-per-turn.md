---
id: 0037-record-push-once-per-turn
title: The artifacts record pushes once per turn
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# The artifacts record pushes once per turn

## Context and problem

264 of 276 commits on main in a day were record commits, each pushed and scanned. They kept main moving under CI runs meant to test a fixed tree.

## Options considered

1. Push on every change.
2. Commit on every change and push once at the end of the turn, before any PR, merge or publish.

## Decision

Push once per turn. Writing commands commit but do not push; the end-of-turn hook pushes, `pending` pushes before it lists, and the after-command hook pushes before `gh pr create|merge|ready`.

## Consequences

Main stops moving under CI, so the tree check can match exactly. A session that dies mid-turn loses that turn's status changes until the next push.

See [the feature spec](../../features/test-cost/spec.md).
