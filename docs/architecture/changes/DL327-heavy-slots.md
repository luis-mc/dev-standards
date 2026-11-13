---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The runner gate has a heavy job class: `runner_gate.heavy_jobs` and `heavy_slots` in machine.json, a heavy slot taken before the CI slot, freed by the job-done hook, reported by the doctor (DL327, D288).
