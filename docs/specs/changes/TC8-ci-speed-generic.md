---
spec: claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---

STACKSPEC §13.1 gains a SHOULD: split the job or step that dominates CI wall time into its own job, and run a splittable test step as parallel shards. The ts template runs its Playwright suite as two shards behind the same required check, and `ci_watch.py` prints a slowest-job summary (slowest job, its share of the run, its two slowest steps) when the runs complete.
