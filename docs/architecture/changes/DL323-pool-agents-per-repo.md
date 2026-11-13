---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The runner pool can run more than one agent for a repository. `pool-add-agent` takes `--route <slug>`; every agent of a repository carries the label `repo-<route>`, so one `CI_RUNS_ON` matches them all. Without `--route`, a new agent for a repository that is already served reuses that route and is named `<route>-2`, `-3`, and so on. `agents.json` stores `route`; old entries route by their slug. The pool image files changed (`templates/runner-pool`).
