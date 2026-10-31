---
id: 0033-packaged-smoke-test-must
title: A packaged program must be smoke-tested in its packaged form
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# A packaged program must be smoke-tested in its packaged form

## Context and problem

A packaged program shipped with a worker that never started while every test passed, because no test ran the packaged form.

## Options considered

1. SHOULD. Products could skip it.
2. MUST. Needs a major STACKSPEC version.

## Decision

MUST, in STACKSPEC 8.0.0 (DL9). CI starts the packaged form and exercises every child process or worker (`smoke_packaged.py`, `smoke.json`). Products claiming 7.x get an upgrade item.

## Consequences

A class of release-only bugs is caught before release. Products that package a program get one more CI step.

See [the feature spec](../../features/delivery-speed/spec.md).
