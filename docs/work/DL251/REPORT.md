# DL251 report

Base: origin/main 9ba28ed. `lede_warnings` was present in project_artifacts.py.

## What changed
- `project_artifacts.py`: new `stale_lede_warnings(rec)`; `check` adds it to its warnings; `render` prints the same line as a `note:`.
- Only test (a) is built: the lede names RELEASE-n lower than the newest Live release. Test (b) is not built: the record keeps no content change times, and git log is not reliable (shallow clones, uncommitted record).
- `render_artifacts.py` unchanged (the check needs the registry, so it lives in project_artifacts.py).
- New `tools/test_artifacts_dl251.py` (5 cases), registered in `.claude/suites.json`.
- Spec rule R5.37a in docs/features/artifacts/spec.md (that spec has no R5.37; the lede rule is ARTIFACTSPEC R5.37 in claude/plugins/docs/references/artifactspec.md).
- Notes: features/artifacts and features/docs DL251.md, docs/architecture/changes/DL251-stale-lede-warning.md.

## Tests
- python3 tools/test_artifacts_dl251.py: 5 passed, 0 failed
- python3 tools/test_project_artifacts.py: 139 passed, 0 failed, 1 skipped
- test_artifacts_dl173 8 passed; dl238 6 passed; ar67 3 passed
- docs_check.py: only W1 on docs/work (expected) and an M1 warning that the new test file is mapped by no spec
- spec-lint dispatch areas=artifacts,docs: artifacts job, docs plugin, areas: success; docs check failed only on W1

## Follow-ups
- Add R5.37a to claude/plugins/docs/references/artifactspec.md (not owned here).
- Map tools/test_artifacts_dl251.py in a spec `code:` list (M1 warning).

Branch head SHA: see `git rev-parse origin/DL251-stale-lede-warning`.

READY
