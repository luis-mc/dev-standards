# DL265 report

Base check: DL-06 is in hook_pre_tool.py; ci_watch.py exists. Branch made from origin/main.

## What changed
- hook_pre_tool.py: when no ledger train carries the PR, the DL-06 refusal says the PR is not linked and prints `delivery_ledger.py link --pr N --sha <head sha> --branch <head branch>`, then `ci_watch.py <sha>`. It fills the values from `gh pr view`, else placeholders. A linked PR without green CI keeps the old message.
- ci_watch.py: after recording, if no train records the sha as its CI head, it prints the one-line hint to stderr (replaces the old "no train matched" line). It never links.
- Spec R5.38 updated. Notes: docs/features/delivery/changes/DL265.md, docs/architecture/changes/DL265-merge-link-hint.md.
- New tests: claude/plugins/delivery/tests/test_dl265_merge_link_hint.py.

## Tests
- `python3 -m unittest test_dl265_merge_link_hint test_dl127_ci_watch_ledger test_dl247_ci_watch_give_up`: 23 ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- tools/test_delivery_hooks.py: not run locally (session guard: heavy suite); ran in CI.
- `gh workflow run spec-lint.yml --ref DL265-merge-link-hint -f areas=delivery` (run 43119348266): every delivery job success, including "plugin ledger, recorder, watcher and hooks". Only "docs check" failed, on the expected W1 for docs/work/.
- docs_check.py locally: only W1. M1 for delivery-speed is cleared by `Docs: none` in the commit message.

## Follow-ups
- Strip docs/work/ before the join (docs_work.py strip).
- DELIVERYSPEC DL-06 row is outside my files; unchanged.

READY
