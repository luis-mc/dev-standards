---
id: 0030-delivery-hooks-and-watcher
title: Hooks enforce in sessions, a watcher acts on time
status: accepted
date: 2026-10-14
supersedes:
superseded_by:
type: explanation
---
# Hooks enforce in sessions, a watcher acts on time

## Context and problem

Delivery lessons lived in memory notes that an orchestrator had to remember. Some steps (merge at green, push the next train) cannot wait for a model turn.

## Options considered

1. Hooks only. Cheap, but nothing acts while no session runs.
2. Watcher script only. Acts on time, but cannot stop a bad turn.
3. Hooks inside sessions plus a watcher script with no model.

## Decision

Hooks and a watcher together. The Stop hook blocks with a ceiling (default 3 blocks, then the turn ends), the PreToolUse hook denies, and `delivery_watch.py` pushes the next train, opens its PR and merges at green on the current head (`--match-head-commit`, never `--auto`). Cloud agents come first; a local `Agent` call needs a `PC-bound:` reason or a full cloud cap.

## Consequences

Rules become checks, and a lesson once enforced loses its memory note. A watcher must be running; SessionStart says when none has a fresh heartbeat. Normative rules stay in DELIVERYSPEC.

See [the feature spec](../../features/delivery/spec.md).
