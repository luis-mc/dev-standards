---
id: 0032-delivery-speed-plan
title: Each delivery layer does its own share of testing
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# Each delivery layer does its own share of testing

## Context and problem

In one measured product each change ran the full suite 4 to 6 times, 56% of CI job-minutes went to cancelled or failed runs, and a finished change waited for its whole train.

## Options considered

1. Test less everywhere. Loses real catches.
2. Keep the checks, remove repeats: stale-result tolerance for inert paths, a quick join check, train freeze, runner health, build workflows only when their inputs change.

## Decision

Keep the checks and remove the repeats (DL1 to DL10). `gate.json` gets `inert_paths`; `join.py` runs install, build, types and the union of affected tests plus dependents; the pre-push hook freezes a train while its CI runs (offline: allow and warn; `DELIVERY_FREEZE_OVERRIDE=1` overrides); `join.py` and `ci_watch.py` warn about runners; dev-standards adopts the log and the freeze. Released as STACKSPEC 8.0.0.

## Consequences

A change waits less and CI restarts less. Warnings, not blocks, for runner health. The numbers stay on the feature page, not in the specs.

See [the feature spec](../../features/delivery-speed/spec.md).
