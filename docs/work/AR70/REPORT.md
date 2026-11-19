# AR70 report

Branch: AR70-publish-copy-fresh

## Files
- claude/plugins/docs/scripts/project_artifacts.py: refresh_publish_copy (called from run_change), render_line, task-add warning
- claude/plugins/docs/scripts/hook_end_of_turn.py: three-step order in the hook text
- claude/plugins/docs/rules/project-artifacts.md: one rule line
- claude/plugins/docs/references/artifactspec.md: R9.12, R6.15
- docs/features/artifacts/spec.md: R5.18, R5.19 and test rows
- tests: new test_ar70_publish_copy.py; test_dl239 assertion updated to the new render wording
- change notes: plugin, artifactspec, features/artifacts

Not done: item e (copy written_at on the page); it would change the page hash.

## Tests
- `python3 -m unittest tests/test_ar70_publish_copy.py` (8): OK
- `python3 -m unittest` for test_dl228, test_fold, test_ar70 (22): OK
- test_dl239, test_ar69, test_dl250, test_dl305 (34 with the hook run): OK
- `cd tests && python3 -m unittest test_hooks` (16): OK
- heavy area advice (`gh workflow run`) not run: workflows are not allowed.

## docs_check
`python3 claude/plugins/docs/scripts/docs_check.py`: M1 cleared by the `Docs: none` commit line. One W1 error remains: the report under docs/work/ is expected on an agent branch and is stripped before the join (docs_work.py strip). No other findings.

Branch head: see `git rev-parse HEAD` of AR70-publish-copy-fresh (the final commit).

READY
