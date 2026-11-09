# DL148 report

## What changed
- `rust/.github/workflows/ci.yml`: `verify` and `integration` now have the DL147 comment line and `needs.decide.result != 'failure'` after `!cancelled()`. The rest of each condition is kept.
- `tools/test_delivery_ci.py`: `IF_COND` has the new clause; `PLAN_CLAUSE` also accepts `needs.plan.result != 'failure'`; new `E2E_AGGREGATE_COND` for the ts `e2e` aggregate job; one new mutation case (removing the `decide.result` clause must be detected).
- `tools/test_ci_speedups.py`: the failing case `nightly_template_structure` came from DL147 (nightly-full.yml `if:` changed). The expected condition and its mutation target now use the new text.
- Merge of DL147 into the DS201 base was clean (no conflict).

## Tests
- `test_dl147_workflow_needs.py`: 5 tests OK (local).
- `test_ds201_rust_workflows.py` (the only ds201 test): 12 tests OK (local).
- `tools/test_delivery_ci.py` and `tools/test_ci_speedups.py`: session_guard blocks full local runs (heavy suites). Run in CI only (spec-lint, areas=delivery):
  - run 42674452169: delivery-ci failed `workflows_conform` on the ts `e2e` job (fixed with `E2E_AGGREGATE_COND`).
  - run 42675081840: delivery-ci passed; ci-speedups failed `nightly_template_structure` (fixed).
  - run 42675570725 (final): all delivery jobs success: CI scripts and workflow templates, train cleanup, setup preflight, area mapping, branch gate and trust rule, artifact pruning, packaged-program smoke test, plugin ledger/recorder/watcher/hooks, change notes enforced and folded, runner plan, and the delivery summary job. Shard matrix skipped.
- docs check job: fails on W1 (docs/work reports on the branch). Expected.

Docs: none, test and template fixups for DL147 and DS201.

Branch head: see the last commit of DL148-workflow-guard-fixups.

READY
