---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---

The agents rule splits branch testing by weight: a light change (specs, profiles, rules, skill text) tests locally only; a heavy change (the `delivery` or `artifacts` area) runs a 1-2 minute local smoke and then `gh workflow run spec-lint.yml --ref <branch> -f areas=...` instead of the full local suites. `tools/ci_areas.py --branch-advice` says which applies.
