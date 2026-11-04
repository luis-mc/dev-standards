# AR56 report (AR56, AR57, AR58)

Branch: AR56-release-numbers. Ships in RELEASE-41.

## Files changed
- claude/plugins/artifacts/scripts/project_artifacts.py
- tools/test_project_artifacts.py, tools/test_render_artifacts.py
- claude/plugins/artifacts/references/artifactspec.md (R5.40, R5.42a, R5.45 wording only)
- docs/features/artifacts/spec.md (new R5.11a), docs/features/artifacts/changes/AR56.md
- docs/architecture/changes/AR56-release-numbers.md
- render_artifacts.py: not changed. The timeline already draws a phase across midnight; a new test proves it.

## Decisions
- AR57: `--release` (no value) = max(record highest, ledger highest) + 1, so it can never collide. The ledger is read from `.delivery/ledger.json` `trains[].release_no`, never written. `--release N` sets or corrects; another release task using N is refused.
- AR58: the exact command is given when the Item's number appears in the ledger; otherwise the old advice.
- AR56: only HH:MM phases roll. An end before its start is the next day; later phases (in the order given) continue on that day. Give phases in time order. An end equal to its start is still refused. The old test `agents=18:00-17:30` is now valid, so it uses 18:00-18:00.
- No e2e specs exist for these screens; the render test is the check.

## Ran
- test_project_artifacts.py: 139 passed, 0 failed, 1 skipped (after merging origin/main).
- test_render_artifacts.py: 163 passed, 0 failed (after merging origin/main).
- docs_check.py: only the expected docs/work/ error (the report lives on the branch only) and an older test-cost warning.
- ci_areas advice: heavy artifacts area, run spec-lint workflow areas=specs,artifacts; not run here (no gh).

READY
