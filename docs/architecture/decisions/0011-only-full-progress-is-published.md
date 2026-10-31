---
id: 0011-only-full-progress-is-published
title: Only Full Progress is published to claude.ai
status: accepted
date: 2026-10-10
supersedes:
superseded_by:
type: explanation
---
# Only Full Progress is published to claude.ai

## Context and problem

claude.ai allows 200 artifact publishes a day per account, and every republish counts. At first each task change republished two artifacts, and a project's daily budget ran out.

## Options considered

1. Publish every artifact on every change. Simple, spends the budget.
2. Publish only Full Progress, once per turn; keep feature artifacts as local HTML files. Chosen.

## Decision

Feature artifacts are standalone HTML files in `docs/artifacts/`, opened in a browser and never published. Full Progress is the only published page, once per turn at the end of it, and only when what the owner sees has changed. A limit refusal defers the publish until the reset. A fail-safe publishes at least once an hour. ARTIFACTSPEC decisions D13, D14, D16 and rules R9.1 to R9.11.

## Consequences

Publishes drop from one per change to at most one per turn. Feature pages cannot be shared by link; a person opens the file. The end-of-turn hook enforces the publish. See the [artifacts spec](../../features/artifacts/spec.md).
