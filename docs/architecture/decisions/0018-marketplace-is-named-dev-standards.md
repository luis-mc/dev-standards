---
id: 0018-marketplace-is-named-dev-standards
title: The marketplace is named dev-standards
status: accepted
date: 2026-10-13
supersedes:
superseded_by:
type: explanation
---
# The marketplace is named dev-standards

## Context and problem

The repository, its README and its install lines used more than one marketplace name, and the new plugin needed one name in its install line.

## Options considered

1. Keep the old name in some places. Confusing.
2. One name, `dev-standards`, everywhere. Chosen.

## Decision

The marketplace `name` is `dev-standards`. Every install line uses `@dev-standards`, and the README says a machine that registered it under another name uses that name. `claude-setup` finds the marketplace name the way it does for luismc-artifacts.

## Consequences

One install line per plugin. A machine with an older name must use it. See the [transcript-folds spec](../../features/transcript-folds/spec.md).
