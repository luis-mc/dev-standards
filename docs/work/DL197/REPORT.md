# DL197 report: join keeps the base's docs/work

Base check: join.py has `def strip_temporary_docs` (OK).

## Approach
After `docs_work.py strip --apply`, `strip_temporary_docs(root, base_ref)` restores `docs/work` from
`origin/<default>` with `git checkout <base> -- docs/work` plus `git add -A -- docs/work`, then commits once.
Only when the base has files under `docs/work`; otherwise behaviour is as before. The caller passes
`<remote>/<default_branch>`, the base join.py already uses. Summaries are still collected first.

## Changed
- claude/plugins/delivery/templates/shared/scripts/delivery/join.py (strip_temporary_docs and its caller)
- claude/plugins/delivery/tests/test_dl197_join_keeps_base_docs_work.py (new, 2 tests)
- docs/features/delivery/spec.md (new R5.46), docs/features/delivery/changes/DL197.md
- docs/architecture/changes/DL197-join-keeps-base-docs-work.md

## Tests
- test_dl197_join_keeps_base_docs_work.py: OK (2)
- test_dl111*, test_dl128*, test_dl99*, test_dl113*, test_dl163*: all OK
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed
- docs_check.py: only W1 (this report under docs/work/, expected) and T2 warnings
- spec-lint.yml run 42971443469 (areas=delivery,docs): every delivery job success, docs plugin success,
  delivery scripts job success; skipped jobs skipped. "docs check" failed only on W1 for this report file.

## Follow-ups
- docs_work.py (docs plugin) could learn a `--base` option so the strip itself keeps base files.
- delivery-speed spec maps join.py (M1); covered by a `Docs: none` line in the commit message.

READY
