# DOC8 report: docs paths (PR body, work reports, stack-profile)

Branch `claude/DOC8-docs-paths`, based on `claude/DOC6-docs-followups` (draft PR with that base). The Q5 promote-to-spec improvement is on `claude/DOC6-docs-followups` itself (see DOC6.md).

Status: READY

## Changes
**(a) Ready PR body** (`claude/plugins/delivery/scripts/delivery_watch.py`, `Watcher.pr_body`). The watcher is the script that opens the ready PR (`push_next`). Its body is now the train line followed by `.delivery/docs-summaries.md` (written by `join.py`, DOCSPEC R10.3) when that file exists and is not empty; otherwise it is the train line as before. README row for `watcher.open_prs` says so. Tests: `claude/plugins/delivery/tests/test_watch.py` (summaries present, absent, blank).

**(b) Agent reports to `docs/work/reports/`** (DOCSPEC R10.1).
- Brief template: the report path in the CI-gate paragraph is `docs/work/reports/<task-id>.md`, with a note that `agent_ci.py` still reads the old paths.
- `agent_ci.py` (generated into projects from `tech-stack-setup/assets/tooling/shared/scripts/delivery/`): `report` default is now the list `docs/work/reports/{task}.md`, `docs/work/agents/reports/{task}.md`, `docs/agents/reports/{task}.md`; a report with the `CODE DONE` marker in any of them counts. `report` in `ci-scope.json` or `--report` may be a string or a list; the previous default string is treated as the new default (so a project that wrote it into its config moves along); any other custom string is read exactly as given, no fallbacks.
- This was the only reader of the report path. `join.py` strips `docs/work/`, so reports in the new path are covered; reports left in the old `docs/agents/reports/` are not stripped by `join.py` (this repo's own reports stay there until it migrates).
- Tests: `tools/test_ci_speedups.py` (new path, both old paths, unknown path, old-default string, custom string).

**(c) STACKSPEC section 18**: the Stack Profile lives at `docs/architecture/stack-profile.md`. Wired paths: `preflight.py` accepts either location (new `one_of` group; message names both; on success at the old path it prints a note to move it), `tech-stack-setup/SKILL.md` (deploy path, ledger, audit reads new path else old and treats the old one as a finding), `auth-setup/SKILL.md` and `references/authentication.md` (resolution order lists the new path first, the old one second), eslint and dependency-cruiser asset comments, tooling README, README, change-note examples (CONTRACT.md, change_notes.py). Tests: `tools/test_preflight.py` (new path passes, old path passes with the note, missing names both; 12 cases).

## Version bumps and change notes (no hand edits; folded on main)
`DOC8-delivery-pr-body` delivery patch; `DOC8-brief-report-path` delivery patch; `DOC8-agent-ci-reports` project-setup patch; `DOC8-stack-profile-path` project-setup patch; `DOC8-stackspec-18-path` STACKSPEC minor. (On the DOC6 branch: `DOC8-promote-merge` artifacts minor, `DOC8-artifactspec-promote-merge` ARTIFACTSPEC minor.)

## Tests run (only what was touched; no full suite, no Docker)
- `tools/test_project_artifacts.py` (DOC6 branch): 134 passed, 0 failed, 1 skipped.
- `claude/plugins/delivery/tests` (unittest discover): 265 OK; `test_watch` 50 OK.
- `tools/test_ci_speedups.py`: 21 passed; `tools/test_preflight.py`: 12/12; `tools/test_delivery_gate.py --no-mutants -k join`: 99 checks, 0 failed; `tools/test_change_notes.py`, `tools/test_ci_areas.py`, `tools/test_spec_check.py`: pass.
- `spec_check.py` on invariants.md (0 errors) and artifactspec.md (0 errors, 1 old numbering warning); `change_notes.py check --config tools/change-notes.json`: ok; `claude plugin validate` on the marketplace, artifacts, delivery, project-setup: pass.
- Not run: GitHub CI, mutation passes, `template_build_check.py` (needs a track and a build).

## Notes for projects
- A project already generated needs the new `agent_ci.py` and `preflight.py` copied in (tech-stack-setup update); until then its old copies keep reading `docs/agents/reports/` and `docs/specs/stack-profile.md`, so nothing breaks.
- This repo has no root CLAUDE.md; conventions were taken from README.md and the DOC6 report. Its own stack profile does not exist (it is a plugin repo), so nothing in it moves.
