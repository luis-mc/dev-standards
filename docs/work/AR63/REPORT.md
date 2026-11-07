# AR63 AR64 AR65 report

## Changes
- AR63 (D21): the stale-copy refusal in `project_artifacts.py` names the steps in order: `pending --json --refresh`, publish the copy unedited with the Artifact tool, `mark-published` again. No auto-refresh; the R9.11 check is unchanged. `hook_end_of_turn.py` adds: make every status change first, then run pending, then publish.
- AR64 (D22): `normalise_expected` in `task-add` and `set-task-status` (the only commands with `--expected`) turns `DD Mon HH:MM` into `DD Mon ~HH:MM`, keeping a `; note`. R6.6 updated.
- AR65 (D23): Expected is optional on To do and On hold in `task-add` (stored empty); `check` accepts it; renderers show `Not scheduled` (`render_artifacts.py`, including its own verifier); `set-task-status` to Running or Waiting with no Expected is refused.
- `artifact_hourly.overdue_tasks`: read, no change needed. An empty Expected does not match the pattern, so the row is skipped. Not edited.
- Docs: R5.11b, R5.11c in the feature spec; artifactspec R6.6 and R9.11; two skills; change notes (plugin, spec, features AR63 to AR65).
- CI: step in spec-lint.yml and `artifacts-ar63` in .claude/suites.json.

## Tests
- `python3 -I tools/test_artifacts_ar63.py`: 6 passed, 0 failed
- `python3 -I tools/test_artifacts_ar60.py`: 6 passed, 0 failed
- `python3 -I tools/test_artifacts_ar59.py`: 9 passed, 0 failed
- `python3 -I tools/test_project_artifacts.py test_pending test_mark test_task_add test_set_task_status test_status expected`: 24 passed, 0 failed
- `python3 -I tools/test_render_artifacts.py expected`: 4 passed, 0 failed (the filter may match nothing; the file ran)

## docs_check
- G1 decisions.md stale: expected on a branch.
- M1 test-cost spec: the workflow file is mapped to it; commit says `Docs: none, one CI step added`.
- M1 warning: tools/test_artifacts_ar63.py is not mapped by any spec `code:` (same as the other ar test files; not mine to map).

Branch head SHA: see the last commit on AR63-artifacts-bugs.

READY
