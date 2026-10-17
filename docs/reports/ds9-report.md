# DS9: generic CI speed-ups (shard balancer, area select, nightly if moved)

Branch `DS9-ci-speedups` (from `origin/main`), integration branch `DS9-integration`. Basis: comics-organizer, 17 Oct: PR CI 34 min, about 60 min of Linux jobs queued on two runners, shards uneven (4 to 12 min), every release ran all 165 integration files. That project builds its own versions (`claude/CO240-faster-ci`, `claude/CO243-integration-by-area`); the generic parts are lifted here, none of its maps.

## What changes (status: branch done, integration fold next)
1. `shared/scripts/delivery/shard_balance.py`: files of shard K of N by greedy longest-first on a committed timings file (`scripts/delivery/ci-timings.json`, path configurable); an unmeasured file gets the median; `update` refreshes the file from a vitest/jest or Playwright JSON report.
2. `shared/scripts/delivery/area_select.py`: changed paths + committed map (`scripts/delivery/ci-areas.json`: areas -> path globs -> test globs and jobs, `run_everything`, `docs`, `always_jobs`) -> which areas and jobs run. Unknown and shared paths run everything; docs-only runs none; `--all` for pushes to the default branch.
3. `ts/.github/workflows/nightly-full.yml`: schedule + dispatch, runners from variables; first job compares the default branch head with the head of the last successful run of the workflow and skips everything when equal. Not added for go, rust, dotnet: their `ci.yml` has no area selection, so there is nothing for a nightly to catch up on.
4. `ts/.github/workflows/ci.yml`: new `plan` job (`runner plan: ...`) runs `area_select.py`; `integration` and `e2e-shard` skip only on an explicit `false`; the `e2e` summary accepts a planned skip; the e2e shards run `shard_balance.py` files (fallback: Playwright's `--shard`).
5. Spec: STACKSPEC §13.1 (new SHOULD paragraph) + change note; README/CONTRACT entries; tests `tools/test_ci_speedups.py`, `tools/test_delivery_ci.py` updated for the plan job.

## Checks (touched files only, run once)
- `tools/test_ci_speedups.py`: 8 passed (shard_balance and area_select scenarios plus 17 mutants, nightly structure and its compare step run with bash against a stub `gh`).
- `tools/test_delivery_ci.py`: 60 passed (the structural checker now knows the `plan` job, the plan clause in the job conditions and the planned-skip summary; 7 new mutation cases).
- `tools/test_ci_areas.py` passed (new row for `test_ci_speedups.py`, routed to the delivery area). `tools/spec_check.py`: 0 errors. `change_notes.py check`: ok.
- YAML of both templates and `spec-lint.yml` parses. The `nightly-full.yml` schedule and the live `plan` job cannot run from the sandbox (need the runners and the actions API); the compare logic is exercised with a stub.
