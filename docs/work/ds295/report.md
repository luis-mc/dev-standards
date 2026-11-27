# DS295 report: live CI runs in Full Progress

## Files
- `claude/plugins/docs/scripts/ci_live.py` (new): fetch with an injectable runner, parse, state mapping, timing text, `CLAUDE_ARTIFACTS_NO_GH=1`.
- `claude/plugins/docs/scripts/project_artifacts.py`: `refresh_ci_runs`, called by `render` and `pending --refresh` before the render; any error warns and keeps the stored runs.
- `claude/plugins/docs/scripts/render_artifacts.py`: `ci_runs_list`; release table (PR row, release rows, own-run rows); task rows (compact cell under Item); the INV-1 check skips the new cell.
- `claude/plugins/docs/templates/project-artifact.css`: `.ci-live*` rules on the existing `.ci-chip`.
- `docs/features/artifacts/spec.md`: R5.39 to R5.41, R6.1 wording, tests table, Source and Tests lines. Change notes: `docs/features/artifacts/changes/DS295.md`, `docs/architecture/changes/DS295-live-ci.md`.
- Tests: `claude/plugins/docs/tests/test_ds295_live_ci.py` (9 cases); `CLAUDE_ARTIFACTS_NO_GH=1` in `tools/test_project_artifacts.py` base_env, `tools/test_artifacts_dl238.py`, `test_dl239_badge_colour_fonts.py`.

## Results
- test_ds295_live_ci.py: 9 passed.
- test_dl239_badge_colour_fonts.py: 17 passed.
- tools/test_artifacts_ds256.py (release tree render): 6 passed.
- tools/test_artifacts_dl238.py: 5 passed, 1 failed (`writes_to_local_dir`). It fails the same way on the unchanged base branch, so it is not from this task.
- tools/test_project_artifacts.py: 140 passed, 0 failed, 1 skipped.
- tools/test_render_artifacts.py: 163 passed, 0 failed (run in the same background batch, before the last INV-1 edit may have landed).
- docs_check: 0 errors, 0 warnings.

## Contract points not met or open
- `docs/design-system/` is empty on this branch, so no design-system rule IDs could be cited. The chips follow the existing `.ci-chip` and checklist status colours; the spec cites R5.40.
- The release tag is read from an optional `tag` (or `version_tag`) field on the release task; nothing sets it yet, so tag runs show only when a project stores it.
- The branch-run lookup for a task without a PR uses one `gh run list --limit 100` and filters on `<task-id>-*`; very old runs are missed.
- No live gh call was made; all checks use a fake runner.
