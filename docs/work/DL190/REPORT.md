DL190 report (in progress)

Base check: `git fetch origin DL187-ci-templates-pool && git checkout -B DL190-pool-integration-job origin/DL187-ci-templates-pool`; test_dl187_ci_templates_pool.py exists.

## What changed
- rust and ts ci.yml: `integration` (hosted: postgres service, today's DATABASE_URL, if: ... && !pool) and new `integration-pool` (no services key, no DATABASE_URL, if: ... && pool, DELIVERY_SHARD: integration-pool). Same `name:`. The empty-image and conditional DATABASE_URL expressions are gone. Steps after the pool env step are copies; test_dl190 checks they stay identical (the template has no shared-step syntax).
- pool-db-env already appends each KEY=value of $HOME/db.env to $GITHUB_ENV (it prints no exports), so the pool step uses it as is; the db.env fallback also writes $GITHUB_ENV.
- ts `e2e`: needs both jobs, cancelled-check for both, dispatch step accepts success/skipped from both, status step lists both results.
- tools/test_delivery_ci.py: FAMILY_JOBS allows `integration-pool`; the if: check strips the pool clause; new check_pool_pair requires same name, services only on hosted, and the exact pool / not-pool clauses. Nothing else is allowed.
- Spec R5.53 reworded; feature note DL190; change note DL190-pool-integration-job.

## How a skipped twin is handled
- ts `e2e` is the only aggregator; it already judges results itself and treats skipped as fine. Both twins are in its needs, with the same success|skipped rule. Rust has no aggregator.
- ci_rerun_first.py groups jobs by name key: a skipped twin plus a success counts as passed (skipped is not in NOT_PASSED); both skipped while selected is held as before.
- A skipped job reports as skipped, which satisfies a required check of that name.

## Tests
- unittest discover over claude/plugins/delivery/tests: 1240 OK (1 skipped).
- tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed.
- docs_check.py: W1 (docs/work, expected) and T2 warnings; M1 for delivery-speed handled by the commit trailer below.
- spec-lint run 42935857453 (areas=delivery,docs): all delivery jobs success (area mapping, branch gate, setup preflight, train cleanup, runner plan, ledger/watcher/hooks, change notes, packaged-program smoke, CI scripts and workflow templates, artifact pruning, scripts/templates/cleanup/prune), docs plugin success, areas success; docs check failed on M1 and W1 only. A rerun follows this commit.
- Coverage: spec-lint's delivery job discovers tests/; no ci_areas.py or suites.json change needed. No mutation passes, no Docker.

## Follow-ups
- Edited outside the owns list because the pair broke them: test_dl181_ci_rerun_first.py and test_dl183_rerun_first_pending.py (job-set assertions).
- Not run on a real pool runner.
- The ts `pnpm turbo migrate` step is unchanged.

Head before this commit: e9e0273
