# DL147 report

## What changed
- New `claude/plugins/delivery/tests/test_dl147_workflow_needs.py`: a stdlib reader of job blocks (jobs, needs, if) and a checker for every `.yml` under `templates/*/.github/workflows/`. Unit tests use inline good and bad samples.
- Fixed jobs (add `!cancelled()` first and `needs.<name>.result` checks):
  - dotnet, go `ci.yml`: `verify`, `integration` (`needs.decide.result != 'failure'`; a skipped decide is fine).
  - ts `ci.yml`: `plan`, `verify`, `integration`, `e2e-shard` (`!= 'failure'` for decide and plan); `e2e` (aggregate, judges results itself, so `!= 'cancelled'`).
  - ts `nightly-full.yml`: `integration`, `e2e` (`!cancelled() && needs.changed.result == 'success'`).
- Notes: `docs/architecture/changes/DL147-workflow-needs-guard.md`, `docs/features/delivery/changes/DL147.md`.
- `.claude/suites.json` not touched: the new test needs no declaration.

## Findings in files I do not own (rust template)
- `rust/.github/workflows/ci.yml` job `verify` needs `decide`: `if:` must check `needs.decide.result`.
- `rust/.github/workflows/ci.yml` job `integration` needs `decide`: same.
- `rust/.github/workflows/package.yml`: no finding.
Fix for both: `!cancelled() && needs.decide.result != 'failure' && needs.decide.outputs.skip != 'true' && ...` plus the DL147 comment line above `if:`. Until then `test_every_template_workflow` fails.

## Breakage outside my files (orchestrator, at the join)
- `tools/test_delivery_ci.py` hard-codes `IF_COND` (line 1276) and the mutation text (line 1638). It now fails 2 cases because of the new `needs.decide.result != 'failure'` clause (and the `e2e` / nightly forms). Update `IF_COND` and `PLAN_CLAUSE` handling there.
- `tools/test_ci_speedups.py` has 1 failing case; not yet confirmed whether it is from this change or earlier. session_guard blocked a re-run (heavy suite), so CI decides.

## Tests
- `python3 tools/ci_areas.py --branch-advice`: heavy, run areas specs,delivery,artifacts,profiles,transcript-folds,docs.
- `python3 claude/plugins/delivery/tests/test_dl147_workflow_needs.py`: 4 pass, 1 fail (rust findings above).
- `python3 tools/test_delivery_ci.py`: 76 passed, 2 failed (see above; run once, then blocked).
- `python3 tools/test_ci_speedups.py`: 23 passed, 1 failed.
- `python3 tools/test_delivery_fallback.py`: OK (28). `python3 tools/test_shard_guard.py`: OK (19).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 2 warnings (T2 on other docs). G1 and W1 not shown.
- spec-lint workflow: see below.

NOT READY
