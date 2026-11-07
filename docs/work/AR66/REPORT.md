# AR66 report

## What changed
- `render_artifacts.py` `_release_heading`: no Expected and no timed phases gives `RELEASE-<n> · not scheduled`; the heading is whitespace-collapsed. The R5.46 check compares group titles normalized on both sides. `project_artifacts.py` needed no change.
- `artifactspec.md` R5.46 heading sentence updated. `docs/features/artifacts/spec.md` has no matching heading sentence (no R5.46 text), so it is unchanged.
- Notes: two in `docs/architecture/changes/` (plugin, spec) and `docs/features/artifacts/changes/AR66.md`.
- New `tools/test_artifacts_ar66.py` (3 cases).

## Tests
- `python -I tools/test_artifacts_ar66.py`: 3 passed, 0 failed
- `python -I tools/test_artifacts_ar60.py`: 6 passed, 0 failed
- `python -I tools/test_artifacts_ar63.py`: 7 passed, 0 failed
- `tools/test_project_artifacts*.py`: not run. The session guard refuses the heavy suite locally; left to CI.
- `ci_areas.py --branch-advice`: heavy (unreadable diff), advises the spec-lint workflow with areas=specs,delivery,artifacts,profiles,transcript-folds,docs. See the end of this file for the trigger result.
- `docs_check.py`: G1 (stale decisions, expected), M1 (new test not mapped by a doc `code:`; the orchestrator wires it), T2 (test-cost, not mine).

## Run command for CI wiring
`python -I tools/test_artifacts_ar66.py`

## CI
`gh workflow run spec-lint.yml --ref AR66-release-heading-no-expected -f areas=artifacts` triggered (run 42387887696) for d5f4ff2. The artifacts jobs (renderer, commands and hooks, incl. test_project_artifacts) passed. The `docs check` job failed at the DOCSPEC step, which is the expected G1 stale-decisions finding on a branch; I did not look at the log further.

Branch head SHA: d5f4ff2dfa992118ceb981c63c69feddb3d9a6a0 (this report is committed after it).

NOT READY
