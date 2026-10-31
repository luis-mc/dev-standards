---
id: 0010-artifacts-never-commit-or-push
title: The artifacts plugin never commits or pushes
status: accepted
date: 2026-10-12
supersedes:
superseded_by:
type: explanation
---
# The artifacts plugin never commits or pushes

## Context and problem

The plugin committed and pushed its record to the default branch on every change. In a project with paid deploys this triggered a deploy on every record change. The plugin also kept the record in a separate git worktree.

## Options considered

1. Keep committing, push less often. Fewer deploys, but the plugin still writes git state the project did not ask for.
2. Write files only. The record lives in `docs/artifacts/` of the working tree, and the project commits it when it chooses. Chosen.

## Decision

The plugin writes files and never git state. No script or hook runs a git write or a `gh` command that writes. The record worktree is retired, and an old one is copied into the working tree once, when it is newer. The commands `commit` and `push` are removed. This is ARTIFACTSPEC 1.8.0 (rules R4.13 to R4.17, R4.24 to R4.29, R8.16, R8.17; decision D23).

## Consequences

A record change never triggers a deploy by itself. The record is uncommitted until the project commits it, so a session must not lose it by switching branches carelessly. Tests spy on every git call and fail on a write (`test_only_read_only_git_is_run`, `hooks_never_write_record`). The feature spec is [artifacts](../../features/artifacts/spec.md).
