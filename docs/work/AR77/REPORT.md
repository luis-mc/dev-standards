# AR77 report: Where it stands built from the record

## Files
- claude/plugins/docs/scripts/render_artifacts.py: `feature_stands`, `_id_runs`, section 1 cell uses it
- claude/plugins/docs/scripts/project_artifacts.py: fingerprint uses the derived cell; `stale_lede_warnings` also warns on train labels and `#NN`
- claude/plugins/docs/references/artifactspec.md: R5.53, R5.54, R5.37 note, conformance row
- docs/features/artifacts/spec.md: R5.23 and test row; docs/features/artifacts/changes/AR77.md
- docs/architecture/changes/AR77-where-it-stands.md (plugin) and AR77-where-it-stands-spec.md (spec)
- claude/plugins/docs/tests/test_ar77_where_it_stands.py (new, 10 tests)
- tools/test_render_artifacts.py and tools/test_project_artifacts.py: section 1 text and one pending case updated

## Tests
- `python3 -m unittest claude/plugins/docs/tests/test_ar77_where_it_stands.py`: 10 passed
- `python3 tools/test_render_artifacts.py section_one lede decisions full_progress feature_summary`: 38 passed, 0 failed
- `python3 tools/test_project_artifacts.py` named cases (pending_never_lists, test_pending_and_mark, status_change, does_not_loop, detail_only, pending_refresh, lede, stale, render_, publish_copy): all passed
- `python3 -m unittest` test_ar69_lighter_full_progress, test_ar70_publish_copy: 13 passed
- tools/test_artifacts_ar63.py and tools/test_project_artifacts_hooks.py: no case reads section 1 text (grep); not run in full (heavy), left to CI.

## docs_check
One error, W1: docs/work/AR77/REPORT.md is on the branch by design (AGENTS.md). No other findings. change_notes check: ok.

## Notes
- R5.36 (generated summary) now serves only a feature with no tasks; with tasks the derived cell wins.
- A lede change no longer makes Full Progress pending for a feature with tasks.

Branch head: see `git rev-parse HEAD` on AR77-where-it-stands.

READY
