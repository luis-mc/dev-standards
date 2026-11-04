# DL38 report: CI runs look

Branch DL38-ci-runs-look. All six points done.

Files: render_artifacts.py (CI part), project-artifact.css (CI rules), ci_runs.py, test_ci_runs.py, test_render_artifacts.py, artifactspec.md R5.51, features/artifacts spec + mock-up + picture, two change notes, one feature note.

Decisions:
- ci_runs.py writes `host` / `os` in `where`; hosted runner name is dropped. Renderer shows `Kind · host|os`; cloud always `Claude cloud · fallback`.
- Bookkeeping steps are skipped in ci_runs.py (latest real step; falls back to the last real step started).
- No purple/teal token exists: `--ci-teal` and `--ci-purple` are colour-mix of page tokens, scoped to the section.
- "Today" = the day of the file's `generated_at` (the render never reads the clock).
- Job bar is red when any step failed.

Ran: `python3 -m unittest test_ci_runs` (17 ok); `python3 tools/test_render_artifacts.py ci_runs` (13 passed). Checked render in light/dark at 1100 and 390 px with Chromium: no sideways scroll. docs_check: only W1 (this report, stays on the branch).
Not run: full render suite (heavy, left to CI).
