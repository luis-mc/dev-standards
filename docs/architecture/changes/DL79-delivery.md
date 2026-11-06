---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The runner pool CPU cap now also follows memory: at most one CPU per 1.5 GiB of pool memory, never below 1 (D102). The pool `.env` gets `POOL_CPUSET` and `POOL_CPUS_INT`. Compose pins the cores with `cpuset` so `nproc` matches the cap, and sets `CI_MAX_PARALLEL` for jobs. The doctor warns when the pool has under 1.0 GiB per CPU.
