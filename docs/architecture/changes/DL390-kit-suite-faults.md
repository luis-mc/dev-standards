---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The kit's `test_guardrails.py` no longer exposes a helper named `test_limits`, which pytest collected as a test and errored on in an adopting project. A tools test now runs the shipped suite in a fresh temp repo with a `master` default branch.
