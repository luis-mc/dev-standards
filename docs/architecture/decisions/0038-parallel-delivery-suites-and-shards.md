---
id: 0038-parallel-delivery-suites-and-shards
title: Delivery suites run in parallel jobs with their own mutant flags and shards
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# Delivery suites run in parallel jobs with their own mutant flags and shards

## Context and problem

One serial delivery job was 11.4 of 11.6 minutes, with every suite's mutation pass on for any delivery change.

## Options considered

1. Keep one job.
2. One job per suite, one mutants flag per suite, and the gate mutation pass in 4 shards.

## Decision

One job per suite, one mutants flag per suite from `tools/ci_areas.py`, and `tools/test_delivery_gate.py --shard I/N` run as a matrix of 4 when its mutants are on. A small final job keeps the old required-check name. The PR run fell to 3.0 minutes.

## Consequences

Wall time is the slowest job, but each job repeats setup. Shards need balanced timings.

See [the feature spec](../../features/test-cost/spec.md).
