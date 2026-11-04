# DL31 report: CI runs section

## Files changed
- New: `claude/plugins/delivery/scripts/ci_runs.py`, `tests/test_ci_runs.py`, `tests/test_watch_ci_runs.py`, `tests/fixtures/ci_runs/*`.
- `claude/plugins/delivery/scripts/delivery_watch.py` (new `pass_ci_runs`, flag `ci_runs=True`), `tests/test_watch.py` (two Watcher calls pass `ci_runs=False` so their call lists stay exact).
- `claude/plugins/artifacts/scripts/render_artifacts.py` (section), `project_artifacts.py` (`read_ci_runs`), `templates/project-artifact.css`.
- `tools/test_render_artifacts.py` (10 new `ci_runs_*` cases).
- Docs: `artifactspec.md` R5.51 (+ conformance row), `docs/features/artifacts/spec.md` (R5.14, section picture, mermaid), `ci-runs-mockup.html`, `ci-runs-section.png`, delivery `README.md` subsection.
- Notes: `docs/architecture/changes/DL31-ci-runs.md` (artifacts plugin + artifactspec), `DL31-ci-runs-delivery.md` (delivery plugin), `docs/features/{artifacts,delivery}/changes/DL31.md`.

## Decisions the contract did not settle
- A change note names one plugin, so two notes instead of one file naming both.
- The section is drawn into the publish copy only, not the committed render. The file is git-ignored and changes every minute; the committed render must stay deterministic and drift-free.
- The section is the last numbered section of Full Progress.
- Cloud fallback: a run with a `claim-lost` slot-log row is shown as kind `cloud`, named by the claim holder (read with git ls-remote and fetch, read only). Cloud sessions are not Actions runs, so no separate row is made for them.
- Added optional fields: `slot_start_s`, `fallback`, `run_number`, `run_attempt` on finished rows; `run_number` on active rows.
- Slot-wait bar starts at the slot log's `queued_at`; the part of "Set up job" before `slot_at` is trimmed so the gate wait is not drawn twice.
- Without `ci.fallback.after_min` the "minutes until fallback" is null and shown as "no fallback set".
- Median slot wait uses finished runs with a non-zero wait.
- Finished runs already in the file are reused, so a tick costs jobs calls only for new and active runs.
- Not seen: the approved sample page (not in the repo). Built from the brief's wording.

## What I ran
- delivery unit tests (415 incl. 15 + 5 new): OK. `tools/test_render_artifacts.py`: 156 passed. `test_project_artifacts_hooks`: 101 passed. `test_artifact_prune`: 23 passed. `test_project_artifacts`: 135 passed, 0 failed, 1 skipped (after fixing the publish-copy root; the new publish-copy case is inside it).
- change_notes check: ok. spec_check on artifactspec.md: 0 errors, 1 warning (same as main).
- docs_index build + docs_check: only W1 (docs/work, expected on a task branch). Generated files not committed.
- No e2e specs exist for this page; the render tests are the check. Screenshots at 1100 px light and 390 px dark looked right, no sideways scroll.
- Not run: mutation passes, Docker, real GitHub.
