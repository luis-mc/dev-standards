# AR54 report

Branch: AR54-full-progress-display

## Files changed
- claude/plugins/artifacts/scripts/render_artifacts.py: `shown_item` drops any `RELEASE-<n>` lead of a numbered release; `thin_ticks` thins timeline axis labels.
- claude/plugins/artifacts/scripts/project_artifacts.py: `release_label_problems` (R5.45 check finding; writes refuse it too).
- tools/test_render_artifacts.py, tools/test_project_artifacts.py: new tests; one old assertion changed (an Item `RELEASE-40 cargo` on release 4 now shows `cargo`).
- claude/plugins/artifacts/references/artifactspec.md (R5.42, R5.45 wording).
- docs/architecture/changes/AR54-full-progress-display.md, docs/features/artifacts/changes/AR54.md (change notes).
- Not touched: templates/project-artifact.css (no rule needed), CI runs section.

## Decisions
- Bug 1: on main, labels, group headers, group keys and rider lines already read the stored `release` number, and `--release` numbers highest + 1 across all rows (dropped ones too). I could not reproduce a counter. The drift I could reproduce: an Item that still starts with an older `RELEASE-8` shows next to the stored `RELEASE-9`. Fixed there; the new check finding covers that. If the owner's record shows another cause, I need the record (anonymised).
- Bug 2: NOT reproduced. The timeline and group headers read each release's own fields. A test pins this. No basis text is drawn on release rows in the renderer on main; if the owner saw it in a different script version, I need that output.
- Bug 3: axis labels are now kept by text width plus a gap; first and last always kept. Axis labels at the owner's phases (join 18:51-19:01, agents 19:17-22:35) were already 60 units apart at step 60 on main; the overlap risk is the date labels at midnight and long spans, which the width rule covers. Not reproduced exactly.

## Ran
- python3 -I tools/test_render_artifacts.py: 162 passed, 0 failed.
- python3 -I tools/test_project_artifacts.py release: 11 passed (before the final full run).
- change_notes.py check: ok. docs_check.py: only the expected D9 error (this report lives on the branch).
- python3 -I tools/test_project_artifacts.py (full): 136 passed, 0 failed, 1 skipped.

READY
