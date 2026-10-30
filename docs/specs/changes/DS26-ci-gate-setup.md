---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
New generic delivery scripts `ci_scope.py` (scope rules from `ci-scope.json`), `agent_ci.py` (one `workflow_dispatch` CI run per agent branch head at `CODE DONE`) and `ci_run_times.py` (the `ci-run-times` artifact); `join.py --ci-gate`; the ts `ci.yml` runs by hand (`origin/<default>...HEAD` plan), has an optional scope step and an opt-in `run-times` job; the agents-and-integration rules and `delivery-config.json` accept the CI-gate path.
