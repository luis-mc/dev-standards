# DL106 report: Plugin smoke

## What changed
- `tools/plugin_smoke.py` (new): checks every plugin under `claude/plugins/` (manifest, hook scripts, compile, `--help`, SKILL.md front matter).
- `tools/test_plugin_smoke.py` (new): fake plugins tree; 9 cases.
- `.github/workflows/plugin-smoke.yml` (new): workflow "Plugin smoke", push to main and workflow_dispatch.
- `.delivery/config.json`: new file with `"smoke_workflow": "Plugin smoke"`. The folder `.delivery/` is in `.gitignore` and the file did not exist on main, so it was added with `git add -f`.
- Wiring: `tools/ci_areas.py` (rule: profiles area), `.claude/suites.json`, `.github/workflows/spec-lint.yml` (profiles job step).
- `docs/testing.md`: one paragraph.
- No plugin file changed, so no change note.

## Tests
- `python3 -I tools/test_plugin_smoke.py`: OK (9 tests).
- `python3 tools/test_ci_areas.py`: all checks passed.
- `python3 tools/plugin_smoke.py`: FAILS on real plugins (see below).
- `python3 tools/ci_areas.py --branch-advice`: "heavy: unreadable diff" (no origin diff in the sandbox). The change maps to the profiles area (light). No heavy run done. `gh workflow run` was not tried: gh is not allowed here, and the workflow file is not on the remote until the push.
- `docs_check.py`: G1 (expected); M1 on test-cost spec is covered by `Docs: none, repo CI only` in the commit message; M1 warning for the new workflow (no doc maps it); T2 warning.

## Real plugin failures (not edited)
The skills in these plugins have no `name:` in their front matter (only description):
- audits: compliance-audit, performance-audit, security-audit
- project-setup: auth-setup, claude-setup, tech-stack-setup

Claude Code takes the folder name when `name` is absent, so the check may be too strict. Decision for the orchestrator: add `name` to those skills, or relax the check to `description` only. Until then "Plugin smoke" fails on main.

## Branch head
See `git rev-parse DL106-plugin-smoke` (the commit that holds this file).

NOT READY
