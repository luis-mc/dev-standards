# DL187 report

Base check: `git checkout -B DL187-ci-templates-pool origin/main`; delivery plugin.json version 1.25.0 (ok).

## Design choices
- Pool test: one expression in both templates, `contains(vars.CI_RUNS_ON || '', 'pool-')`. No pool name is hard-coded.
- The project's local workaround `contains(...) && '' || 'postgres:17'` always yields `postgres:17` (an empty string is falsy). The templates use `!contains(...) && 'postgres:17' || ''`, which gives an empty image on a pool runner.
- Job-level `DATABASE_URL` uses the same form: empty on a pool, today's DSN elsewhere. The pool step then sets the real one through `$GITHUB_ENV`.
- Step `Load the pool database env` runs only on a pool runner: `pool-db-env`, else append `$HOME/db.env` to `$GITHUB_ENV`, else `::error::` and exit 1.
- Rust migrations: run `sqlx migrate run --source <dir>` for each existing `migrations`, `apps/*/migrations`, `crates/*/migrations`; install sqlx-cli only if one exists. Rust test targets: `cargo metadata` decides whether `integration` and `route_coverage` exist. I chose discovery over a gate.json list because a fresh skeleton then needs no config and a project with these folders or targets runs them unchanged.

## What changed
- rust and ts `ci.yml` (integration job), new test `claude/plugins/delivery/tests/test_dl187_ci_templates_pool.py`, spec R5.53, feature note `docs/features/delivery/changes/DL187.md`, change note `docs/architecture/changes/DL187-ci-templates-pool.md`.

## Tests
- `python3 -m unittest tests.test_dl187_ci_templates_pool tests.test_ds201_rust_workflows` (in the delivery plugin): 22 OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- Delivery plugin tests matching `*ci*`: 146 OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: only W1 (this report under docs/work, expected) and a T2 warning in delivery-speed.
- `gh workflow run spec-lint.yml --ref DL187-ci-templates-pool -f areas=delivery,docs` (run 42933713439), completed: every delivery job success (setup preflight, train cleanup, branch gate, CI scripts and workflow templates, ledger/watcher/hooks, runner plan, area mapping, packaged-program smoke, change notes, artifact pruning, scripts/CI templates/cleanup/prune/change notes), docs plugin success, areas success; `docs check` failure only for W1 (docs/work report); other areas skipped.
- The new test is covered: the spec-lint delivery job runs `unittest discover` over `claude/plugins/delivery/tests`. No `.claude/suites.json` or `ci_areas.py` change was needed.
- No mutation passes, no Docker.

## Follow-ups
- The ts `pnpm turbo migrate` step is untouched; a pool runner gets its database from the pool env.
- Not run on a real pool runner; workflow YAML parses and the text checks pass.

Branch head SHA: c1b7965c561bbb123d83062c4761c7ff48aca3ba (before this report commit)

READY
