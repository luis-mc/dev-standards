---
id: 0036-retire-fake-renderer-group
title: Retire the artifacts suite's fake-renderer test group
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# Retire the artifacts suite's fake-renderer test group

## Context and problem

The group was written before the real renderer existed. It cost the same per case as the real group and was 46% of the suite. It never caught a bug the real group missed.

## Options considered

1. Keep both groups.
2. Retire the fake group, move its one unique case into the real group.

## Decision

Retire it and move `test_check_runs_check_html`.

## Consequences

About 1.5 minutes less in CI and 8 minutes less per local run. A bug hidden by the real renderer's behaviour could slip; none was found.

See [the feature spec](../../features/test-cost/spec.md).
