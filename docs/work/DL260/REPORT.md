DL260 report: Full Progress UTF-8 charset

Base check: origin/main; full-progress-artifact.html had no charset, feature-artifact.html had `<meta charset="utf-8">`. OK.

What changed
- templates/full-progress-artifact.html now begins with `<meta charset="utf-8">`, then `<title>`.
- render_artifacts.py: the R5.29 check now wants that first line.
- Page audit: feature pages, docs_index.py pages and design_system.py gallery already declare UTF-8 in the head. The local copy is the repo copy; `_with_refresh` only edits a `<head>`, and Full Progress has none, so it needed no change. The publish copy is a fragment the artifact host wraps; it keeps the meta tag, which is harmless.
- tools/test_render_artifacts.py and tools/test_project_artifacts.py (3 lines): expected first line updated.
- New tools/test_artifacts_dl260.py (registered in .claude/suites.json): repo copy, local copy, feature page, template.
- Spec sub-rule R5.17a; notes docs/features/artifacts/changes/DL260.md and docs/architecture/changes/DL260-utf8-charset.md.

Tests
- python3 tools/test_artifacts_dl260.py: 4 passed, 0 failed.
- python3 tools/test_render_artifacts.py (named cases, 44 in all): passed. The full suite is heavy and left to CI.
- spec-lint.yml, areas=specs,artifacts (run 43111985949): "artifact renderer, commands and hooks" and "specs, templates and AUTHSPEC" succeeded; "docs check" failed only on the expected W1 for docs/work/ (local docs_check: nothing else).

Follow-ups: strip docs/work/ before the join (docs_work.py strip). Not run: mutation passes, Docker.

Branch head SHA: see git log (report commit follows 58b7d4e).

READY
