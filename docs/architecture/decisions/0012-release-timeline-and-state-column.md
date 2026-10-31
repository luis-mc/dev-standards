---
id: 0012-release-timeline-and-state-column
title: Releases get a timeline, and Expected is the sum of the phases
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# Releases get a timeline, and Expected is the sum of the phases

## Context and problem

Full Progress listed tasks but did not show which would ship together or when. Estimates were padded by hand and drifted from the real phases of a release. The owner approved a hand-made preview (decision D10 of the feature page).

## Options considered

1. Keep the checklist only, with a release note on each row.
2. Add release tasks with phases and one named risk, a timeline drawn above the checklist, and a State column on the feature table. Chosen.

## Decision

A task may be a release with phases (`agents`, `join`, `ci`, `merge`) and one named risk. Other tasks name the release they ride. A release's Expected time must equal the end of its last phase and a mismatch is refused. Full Progress draws a deterministic SVG timeline of open releases, and its feature table gets a State column. A risk is named, not added as padding. ARTIFACTSPEC sections 5.7 and 5.8.

## Consequences

Estimates become derived and auditable. Writing commands gain flags (`--release`, `--phase`, `--risk`, `--rides`). The record format string stays valid because the new fields are optional. See the [artifacts spec](../../features/artifacts/spec.md).
