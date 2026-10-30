---
plugin: claude/plugins/project-setup/.claude-plugin/plugin.json
change: minor
---
New generic delivery scripts `ci_scope.py` (scope rules from `ci-scope.json`), `agent_ci.py` (merges each `CODE DONE` branch onto its base, `--base`, default `origin/master`, into a two-parent commit on `ci/<task>` and starts one `workflow_dispatch` CI run per branch head; conflicts are reported by file) and `cleanup.py --pr N` removes the `ci/<task>` refs of the merged train and `ci_run_times.py` (the `ci-run-times` artifact); `join.py --ci-gate`; the ts `ci.yml` runs by hand (`origin/<default>...HEAD` plan), has an optional scope step and an opt-in `run-times` job; the agents-and-integration rules and `delivery-config.json` accept the CI-gate path.
