---
id: 0031-machine-load-guard
title: The load guard holds new work and never touches running work
status: accepted
date: 2026-10-14
supersedes:
superseded_by:
type: explanation
---
# The load guard holds new work and never touches running work

## Context and problem

Parallel installs and test runs filled memory and crashed the owner's machine.

## Options considered

1. Kill or suspend heavy processes over a limit. Risky: it can destroy work.
2. Hold only new heavy work over a limit. Safe, slower under load.

## Decision

Hold new heavy work only. Limits are 85% memory and 60% CPU, overridable per project and per machine. The guard is on in every project where the plugin is enabled, with or without `.delivery/`. A self-hosted runner hook waits up to 30 minutes for the machine to fall under the limits.

## Consequences

The machine stays usable and nothing is lost. Jobs wait. If the machine cannot be measured, the call is allowed with a warning.

See [the feature spec](../../features/delivery/spec.md).
