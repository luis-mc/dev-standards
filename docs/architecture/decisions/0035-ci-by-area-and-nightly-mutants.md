---
id: 0035-ci-by-area-and-nightly-mutants
title: CI runs the areas a change touches; mutation passes run when their files change
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# CI runs the areas a change touches; mutation passes run when their files change

## Context and problem

Every change ran every suite. A luismc-artifacts patch waited 17.5 minutes where about 3.8 proved the same. Mutants were 81% of the gate suite.

## Options considered

1. Leave CI whole. Slow.
2. Split by area with a shared-path list that runs all, run mutants only when their files change, and run everything nightly.

## Decision

Split spec-lint into area jobs chosen by `tools/ci_areas.py`; shared paths run every area; mutants run when their files or suite change; `nightly.yml` runs all areas with mutants at 03:00 UTC; a push to main that differs from the tested PR only under ignored paths skips the run; a newer commit cancels an older ready-PR run. Agents run affected suites locally and the ready PR is the one full run.

## Consequences

A ready PR for one area waits for that area. A file used by two areas must be in the shared list, which a test checks. Drift is covered by the nightly run.

See [the feature spec](../../features/test-cost/spec.md).
