---
id: 0039-generic-ci-speed-for-products
title: Generic CI speed is a SHOULD in STACKSPEC 13.1
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# Generic CI speed is a SHOULD in STACKSPEC 13.1

## Context and problem

The dev-standards CI speed-ups were found by measuring. Products have no mutation pass, so the generic form is about the dominant job.

## Options considered

1. Keep it dev-standards only.
2. A generic SHOULD plus e2e shards in templates and a slowest-job summary in `ci_watch.py`.

## Decision

A generic SHOULD (minor version). A job that takes most of a run gets its own job and splits into parallel shards where it can. The ts template's e2e job is a matrix (default 2 shards, `fail-fast: false`), and `ci_watch.py` prints each run's slowest job without changing the exit code.

## Consequences

Products find the dominant job from data. Small steps stay together because every job repeats setup.

See [the feature spec](../../features/delivery-speed/spec.md).
