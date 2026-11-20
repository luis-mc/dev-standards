# DL379 report

## Changes
- `artifact-prune.yml` template: `workflow_run` removed; runs on the daily cron (`23 3 * * *`) and `workflow_dispatch`. The `workflows:` line stays as a `# workflows: [...]` comment so `--sync-workflow`, `--check-workflow` and the install merge keep working (regex in `artifact_prune.py` and `delivery_ci_install.py` accept the `#` prefix). Rule text in `claude-setup/.../agents-and-integration.md` says "once a day".
- Every job in the shipped templates and in this repo's workflows has `timeout-minutes` <= 30 (added: decide 5, plan 10, verify 15, integration/e2e 30, cleanup 10; spec-lint jobs 10).
- Jobs with `uses:` (the `spec-lint` job in `nightly.yml`) cannot take `timeout-minutes`; the called jobs carry theirs. The guard skips them.
- `spec-lint.yml`: `delivery-gate-shards` skips on `pull_request`; cleanup and change-note suites get `--no-mutants` on `pull_request`. Nightly keeps the mutation runs.
- New `test_dl379_templates_guardrails.py`; `tools/test_artifact_prune.py` updated for the new trigger set.
- Spec: R5.23 and test row; feature note `docs/features/delivery-speed/changes/DL379.md`; plugin note `docs/architecture/changes/DL379-templates-guardrails.md`.

## Timeouts lowered to 30 (projects with slower jobs must split them)
- `shared/ci-fallback.yml` job `shard`: 90 -> 30
- `ts/nightly-full.yml` job `integration`: 60 -> 30
- `ts/nightly-full.yml` job `e2e`: 60 -> 30

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl379_templates_guardrails.py`: OK (4)
- `test_dl122`, `test_dl255`, `test_dl242`, `test_dl150`, `test_dl121`, `test_dl376`: OK
- `tools/test_artifact_prune.py` cases `workflow_structure`, `workflow_checker_catches_each_defect` (called directly; full suite blocked by the session guard): ok
- Not run (heavy, left to CI): full `tools/test_artifact_prune.py`, `tools/test_ci_areas.py`, `tools/test_delivery_ci.py`.

## docs_check
2 errors, both unrelated to my change: G1 `decisions.md` stale (same on origin/main, generated, not committed) and W1 `docs/work/` file (by design, branch only).

## Head
Code commit f29defb (this report is committed after it).

READY
