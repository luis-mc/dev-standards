# AR59 report: artifacts plugin fixes (F20 to F27)

Each finding had a failing test first (all 9 new tests fail on main, pass now): `tools/test_artifacts_ar59.py`.

- F20 fixed. While `deferred_until` is in the future, `hourly_due`, `release_changes` and `publish_hourly.reasons` return nothing, so the Stop hook does not block. The one-line deferred note already comes from `tell_deferred_once`.
- F21 fixed. Per-process temp file and an O_EXCL lock around read, change, write. 8 processes x 5 events keep all 40 (main lost most).
- F22 fixed. A "DD Mon" date in `--started` and `--phase` takes the year nearest now.
- F23 fixed in part. Quotes and operators are read with shlex. The exit code counts only for the last segment or when every later operator is `&&`. Not done: skipping `gh pr merge <n>` for a PR that is not the current branch's (needs a gh call; the hook runs none today).
- F24 fixed. No merged suggestion while the task has an open PR. The "mergedAt later than changed" check is not added.
- F25 fixed. An open row whose Expected is over six weeks in the past is read as a plan for the next occurrence: not overdue (`overdue_tasks`, `_other_row`). No year syntax added.
- F26 fixed. `continue` on an invalid year in both `expected_datetime` loops.
- F27 fixed. `repo_root` decodes UTF-8 with errors='replace'.
- hooks.json: the four commands use the `if command -v python3 ...; else python ...; fi` pattern. `test_project_artifacts_hooks.py` checks the new form.

Tests run: test_artifacts_ar59 9/9; test_project_artifacts 139 passed, 1 skipped; test_render_artifacts 163/163; test_project_artifacts_hooks 101/101; test_artifact_prune 23/23. E2E: none for these files (no screen changed).

Change note: docs/architecture/changes/AR59-artifacts-fixes.md. No spec text changed.

Branch head: see the last commit on origin/AR59-artifacts-fixes.

READY
