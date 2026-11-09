# DL122 report: prune workflow list

## What changed
- `artifact_prune.py` reads `artifact_prune.workflows` (list of workflow names) from `.delivery/config.json` (the file it already reads; `--config FILE` overrides). Unset file, section or key: `["CI", "Package"]` (the template's list).
- New flags: `--print-workflows` (one name per line), `--sync-workflow [FILE]` (rewrites the one-line `workflows: [...]` in FILE, default `.github/workflows/artifact-prune.yml`; prints `synced` or `unchanged`), `--check-workflow [FILE]` (exit 1 if it differs). Bad list (empty, not strings, quote/newline/backslash in a name) or a file with no one-line list: exit 2.
- Why generated, not dynamic: GitHub reads `on.workflow_run.workflows` before any step runs, so it cannot come from a file at run time. Config in `.delivery/config.json` was chosen because the script already reads it there. Run `--sync-workflow` after `delivery_ci_install update`, which restores the template line. The workflow has a final step that warns (never fails) when the list differs; the daily schedule sweeps every workflow's artifacts in the meantime.
- Projects that set nothing: identical behaviour (the template line is unchanged; the extra step only checks).
- Follow-up for the orchestrator: the installer could run the sync itself after install/update (not in my owned files).
- Change note: docs/architecture/changes/DL122-prune-workflow-list.md.

## Tests
- `python3 claude/plugins/delivery/tests/test_dl122_prune_workflow_list.py`: 5 OK.
- `python3 tools/test_artifact_prune.py`: 23 passed, 0 failed (a first run failed on a workflow-checker mutation; fixed by ordering the new step after the delete step and rewording a comment).
- `python3 tools/ci_areas.py --branch-advice`: delivery is heavy, advises spec-lint.yml areas=delivery. See below.
- docs_check: see below.
