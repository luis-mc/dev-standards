---
id: 0013-medium-effort-for-both-models
title: Medium effort for both Opus and Sonnet by default
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# Medium effort for both Opus and Sonnet by default

## Context and problem

The owner first asked for Sonnet at high effort, then confirmed Sonnet at medium everywhere. Evidence from real sessions showed that most work is mechanical and that effort was being set by hand.

## Options considered

1. Opus high and Sonnet high. Highest quality, highest cost, easy to exceed the session limit.
2. Opus medium and Sonnet medium, preselected and asked on every setup. Chosen.

## Decision

The default is medium for both models, in every skill profile, in `claude-setup`, in the architect agent and in the settings template's top-level `effortLevel`. The agent rules tell the main session to pass `effort: "medium"` on every Opus or Sonnet Agent call. Released in luismc-project-setup 13.0.0 (MP7).

## Consequences

Cost drops, and one table (`model-profiles.json`) holds the default. A test fails if any profile drifts from medium (`tools/test_model_profiles.py`, check D1). A project that wants high sets it itself. See the [models spec](../../features/models/spec.md).
