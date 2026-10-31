---
id: 0040-rule-tags-and-blocking-checks
title: Every shipped rule line is tagged, and a check that finds a break blocks
status: accepted
date: 2026-10-11
supersedes:
superseded_by:
type: explanation
---
# Every shipped rule line is tagged, and a check that finds a break blocks

## Context and problem

Shipped rule files mixed checked rules with advice, and nothing said which was which.

## Options considered

1. Warn when a check finds a break.
2. Block.

## Decision

Tag every line of the shipped rule files with its check or `advice`, with a test that fails on an untagged line (`tools/test_rule_tags.py`). A check that catches a break blocks. A suite is heavy when it takes over 3 minutes locally.

## Consequences

Readers see what is enforced. Adding a rule means adding its tag.

See [the feature spec](../../features/test-cost/spec.md).
