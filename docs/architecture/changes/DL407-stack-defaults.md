---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Default e2e spec globs now also match Cypress (`*.cy.*`), `tests/e2e/test_*.py` and nested `e2e/**/*.spec.*`. `agent_ci.py` merges onto the default branch (the target of `origin/HEAD`, else `origin/main`) instead of `origin/master`.
