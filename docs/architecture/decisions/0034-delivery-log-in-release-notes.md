---
id: 0034-delivery-log-in-release-notes
title: The delivery log lives in the train's release notes
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# The delivery log lives in the train's release notes

## Context and problem

The owner wants time-to-live per change, split into waiting, testing and queueing.

## Options considered

1. Commit the log to main. Adds commits that move main under CI.
2. Append it to the train's GitHub release notes.

## Decision

Release notes. `cleanup.py` records times before it deletes a branch; the deploy step adds live. dev-standards is public, so it creates a public release per train. Times are UTC, and CI start is the earliest run on the ready PR's branch since the PR was created (so earlier rounds count as testing, not waiting).

## Consequences

No commits to main for the log. It depends on the GitHub release API; if the branch listing fails it falls back to head-only figures.

See [the feature spec](../../features/delivery-speed/spec.md).
