---
id: apps
title: The apps
type: explanation
owner: owner
last_verified: 2026-10-31
---
# The apps

Each app is one plugin in the `dev-standards` marketplace. The app names here are the values of `apps` in `docs/docs.json` and in each feature spec's front matter. This page does not repeat what a feature does. The feature specs do that.

## luismc-agents

Ships shared custom agents. Today that is the `architect` subagent. It gives a direct recommendation on a hard design call or on audit findings. It flags decisions that belong to the owner.

Features: [agents](../features/agents/spec.md).

## luismc-artifacts

Keeps project status in front of the owner. From a record in the repository, it generates one feature artifact per feature (a standalone HTML file) and one Full Progress artifact per project. Hooks keep the record current. They block the end of a turn until Full Progress is published.

Features: [artifacts](../features/artifacts/spec.md).

## luismc-audits

Three review skills: security, performance and compliance. Each skill reads the code, verifies each finding and hands back a report ranked by severity. It never changes code.

Features: [audits](../features/audits/spec.md).

## luismc-delivery

Turns delivery rules into checks. Hooks and a background watcher read a per-repository ledger and enforce releases, CI, agent launches, owner questions and attribution. It also covers the speed of delivery and the cost of tests.

Features: [delivery](../features/delivery/spec.md), [delivery-speed](../features/delivery-speed/spec.md), [test-cost](../features/test-cost/spec.md).

## luismc-docs

The documentation standard (DOCSPEC) as a plugin. It lays out `docs/` by reader question and builds an offline index. It folds change notes into versions. It checks that docs stay true to the code.

Features: [docs](../features/docs/spec.md).

## luismc-project-setup

Takes a repository from empty to production-ready with three skills: `tech-stack-setup` (stack and delivery tooling, to STACKSPEC), `auth-setup` (authentication, to AUTHSPEC) and `claude-setup` (Claude Code configuration and the model split). It also audits an existing repo against the same specs.

Features: [project-setup](../features/project-setup/spec.md), [models](../features/models/spec.md).

## luismc-specs

Two skills for spec-first work. `spec-new` interviews the owner and writes a numbered spec with testable requirements. `spec-check` validates numbering and cross-references.

Features: [specs](../features/specs/spec.md).

## luismc-transcript-folds

Folds long diffs and finished shell commands in the transcript to one line each. A band above the prompt holds two toggles and a tally of changes made this session. It writes no files.

Features: [transcript-folds](../features/transcript-folds/spec.md).
