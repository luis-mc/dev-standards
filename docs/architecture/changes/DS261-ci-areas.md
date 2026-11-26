---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---

New `changed_areas.py` (areas from the project's `.delivery/ci-areas.json`, unknown path means everything), `ci_areas_check.py` (fails a required workflow with a pull-request path filter; the doctor warns) and the `ci-areas-pattern.yml` snippet: skip by job-level `if` plus an always-run aggregate job (DS261).
