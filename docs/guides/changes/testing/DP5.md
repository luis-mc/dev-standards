---
change: minor
task: DP5
---
spec-lint's docs-check job now waits for the areas job and runs only when a change touches docs/, AGENTS.md, tools/, claude/ or the workflows; tools/ci_areas.py emits a docs_check output.
