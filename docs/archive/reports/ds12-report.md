# DS12 report: release labels without repeated number; set-task-status --item

- `shown_item()` in `render_artifacts.py` drops a release's own `RELEASE-<n>` lead (and `:` or ` · `) from the item in the timeline label and aria text, task table, glance list and `check`. `RELEASE-n0 ...` and a bare `RELEASE-n` are left alone.
- `set-task-status --item TEXT` in `project_artifacts.py`: whitespace-normalised, non-empty, at most 80 characters (the `check` limit), history row `<ID> item changed from "old" to "new"` (feature tasks; project tasks warn).
- ARTIFACTSPEC R5.45 and the command table updated; version bump and change log come from the change note `docs/specs/changes/DS12-release-labels-item.md` (spec and plugin, minor), folded by the orchestrator per that folder's README. The plugin changelog is the same note.
- Tests: `release_number_is_shown_once` (test_render_artifacts), `test_set_task_status_item_corrects_title` (test_project_artifacts). Both pass; neighbouring timeline cases pass.
- The plugin has no `tests/` folder; its tests live in `tools/`, and the session guard refuses full heavy suites locally, so only touched cases ran. CI runs the full suites.
