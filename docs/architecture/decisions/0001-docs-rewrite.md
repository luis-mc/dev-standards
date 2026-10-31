---
id: 0001-docs-rewrite
title: Rewrite every doc to DOCSPEC, requirement IDs kept
status: accepted
date: 2026-10-31
supersedes:
superseded_by:
type: explanation
---
# Rewrite every doc to DOCSPEC, requirement IDs kept

## Context and problem

dev-standards adopted luismc-docs on 31 Oct 2026 (DS109): the files moved, but their content kept its old shape. DOCSPEC D15 plans a full rewrite as a follow-up. Projects, hooks and tests cite the shipped specs' requirement IDs (R4.24, U7, DL-nn) and section numbers, so a rewrite must not break those citations.

## Options considered

1. Gaps list only: rewrite pages as they are touched. Cheap, slow to converge.
2. Plan the rewrite as a spec first, rewrite later.
3. Rewrite everything now, in one release. Chosen by the owner.

For the shipped specs (ARTIFACTSPEC, DOCSPEC, STACKSPEC, AUTHSPEC, DELIVERYSPEC):

1. Layout and wording only, every ID and section number kept. Chosen.
2. Renumbering allowed, every citation updated, major versions.
3. Wording only.

For the old reports, train plans, contract and upgrade note:

1. Reports stay unchanged in `docs/archive/reports/` (history). Chosen.
2. Plans, the AR50 contract and the STACKSPEC 8.0.0 upgrade note fold into feature specs and MADRs; the originals move to `docs/archive/`. Chosen.

Feature specs: one per plugin, plus the five feature pages promoted with `promote-to-spec`. Chosen.

## Decision

Release C rewrites every doc this round with parallel agents on short-lived branches, joined on main and deleted at once. The shipped specs gain a reader-first preamble (in one paragraph, why, how it works with a diagram) before section 0. Their sections, requirement IDs, `**Version:**` lines and change-log headings stay where they are, and each gets a minor version through a change note. No owner review before the merge; CI green merges.

## Consequences

Every page reads the same way, and nothing that cites a spec breaks. The shipped specs get longer by their preamble. Decision records are numbered in ranges per agent so parallel branches never collide.
