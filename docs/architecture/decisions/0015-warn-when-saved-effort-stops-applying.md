---
id: 0015-warn-when-saved-effort-stops-applying
title: Warn at session start when a saved effort stops applying
status: accepted
date: 2026-10-10
supersedes:
superseded_by:
type: explanation
---
# Warn at session start when a saved effort stops applying

## Context and problem

Effort is saved under the full model ID while the model is chosen by alias. When an alias moves to a newer model, no entry matches and the model runs at its default effort until `claude-setup` runs again.

## Options considered

1. Do nothing and rely on the default. Silent drift.
2. Write an entry for an alias, not an ID. Not supported by the settings format.
3. A session-start hook that warns when the active model ID has no entry. Chosen.

## Decision

`effort_drift.py` runs at session start and shows a one-line warning when the active Opus or Sonnet ID has no saved effort. It can be turned off with `CLAUDE_SETUP_EFFORT_DRIFT=off`.

## Consequences

The owner learns of the drift when it happens. With medium saved for both models the fallback is the same value, so the warning matters once a higher effort is chosen. See the [models spec](../../features/models/spec.md).
