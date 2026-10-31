---
id: 0014-leave-explore-and-plan-on-opus
title: Leave Explore and Plan on Opus
status: accepted
date: 2026-10-10
supersedes:
superseded_by:
type: explanation
---
# Leave Explore and Plan on Opus

## Context and problem

The built-in Explore and Plan agents follow the main session's model, so they run on Opus. An early inventory wrongly said they ran on Sonnet. Overriding them costs a plugin agent with the same name.

## Options considered

1. Override both with Sonnet agents. Cheaper searches, but a plugin shadows a built-in.
2. Leave both on Opus. Chosen.

## Decision

Plugins do not override Explore or Plan.

## Consequences

Searches and plans cost Opus tokens. Nothing in the plugins shadows a built-in agent. See the [models spec](../../features/models/spec.md).
