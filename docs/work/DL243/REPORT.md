# DL243 report

Base check: origin/main fetched; docs_fold.py exists; DELIVERYSPEC has a `**Version:**` line. OK.

## What changed
- `docs_fold.py`: a doc with a body `**Version:** X.Y.Z` line and no `version:` front matter is bumped in place. A row is added only under an existing `## Versions`, `## Change log` or `## Changelog` table (DELIVERYSPEC has none, so nothing else is added). No front matter, no new table. A doc with both forms is refused (exit 2, file and notes untouched). Front matter docs behave as before.
- New tests: `claude/plugins/docs/tests/test_dl243_version_line.py` (4 tests).
- Spec: R5.9a in `docs/features/docs/spec.md`; notes `docs/features/docs/changes/DL243.md` and `docs/architecture/changes/DL243-fold-version-line.md`.

## Tests
- `python3 -m unittest test_dl243_version_line test_fold test_ds184 test_du4 test_check test_hooks` (in claude/plugins/docs/tests): all OK (4, 10, 14, 15, 22, 16 tests).
- `docs_check.py`: only G1 (stale generated decisions.md) and W1 (docs/work on branch); both are accepted per brief.
- spec-lint run 43086887655 (areas=docs, workflow_dispatch): "which areas": success; "docs plugin": success; "docs check": failure, only G1 and W1; all other jobs skipped (not in area).

## Follow-ups
- G1: decisions.md is stale on main; regenerate with docs_index.py build at the release.
- W1: strip docs/work before the join.

Branch head before this commit: 45d6ea10efb0957a67c4bc7540d97c19a3798e43

READY
