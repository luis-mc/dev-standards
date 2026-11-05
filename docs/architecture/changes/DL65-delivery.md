---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Two runner pool fixes. The pool CPU cap stays strictly below the CPUs Docker sees: the setup reads `docker info --format {{.NCPU}}` (else the `.wslconfig` processors value, else the host CPUs) and caps `POOL_CPUS` at NCPU - 1, never below 1, so Docker accepts the container on recreate. After the step that sets `CI_RUNS_ON`, the setup reads the local checkout's workflows (when `--repo-path` names one) and warns which workflows have `runs-on:` but never read `vars.CI_RUNS_ON`; the step still passes.
