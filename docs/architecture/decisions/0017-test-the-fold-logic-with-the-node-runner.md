---
id: 0017-test-the-fold-logic-with-the-node-runner
title: Test the fold logic with Node's own test runner
status: accepted
date: 2026-10-13
supersedes:
superseded_by:
type: explanation
---
# Test the fold logic with Node's own test runner

## Context and problem

A mod runs inside Claude Code, and its test kit is not part of this repository. Pulling in a test kit or npm packages would add a dependency to a plugin that has none.

## Options considered

1. Use Claude Code's mod test kit. Tests the glue, adds a dependency.
2. Keep every decision in pure TypeScript files and test them with `node --test`. Chosen.

## Decision

The decisions live in `hooks/fold/*.ts`, with no engine import, no JSX and no Node API. `transcript_folds.tsx` is glue only. `purity.test.ts` checks the rule. Node runs the `.ts` files directly.

## Consequences

The plugin needs no npm package. The glue in the `.tsx` file is not covered by the Node suites and is checked by a smoke run. See the [transcript-folds spec](../../features/transcript-folds/spec.md).
