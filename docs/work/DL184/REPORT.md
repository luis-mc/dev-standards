# DL184 report: pool, apply and doctor agree

Base check: `git fetch origin main && git checkout -B DL184-pool-doctor-agree origin/main`; `claude/plugins/delivery/.claude-plugin/plugin.json` version is 1.24.0 (ok).

## Root causes
1. **Stale layer check.** `_layer_checks` took the image from `docker ps --filter label=... --format '{{.Names}} {{.Image}}'`. After a rebuild moves the tag, `docker ps` prints the old image ID. Now `container_image()` reads `docker inspect -f '{{.Image}}'` on `pool-<name>-pool-1`, and falls back to the tag `luismc-runner-pool:<name>` only when no container runs.
2. **Template drift.** Each side compares against the templates of the plugin version that runs it. A pool written by a newer plugin looked like drift to an older doctor, and `pool-refresh` from the older plugin would have written older files over it. Now the pool folder records the writer in `pool-version.json` (written by `copy_pool_templates`). `pool_files_state()` returns ok, newer (warn: "written by X, newer than this project's Y: update the plugin here") or drift (warn: pool-refresh). `refresh_plan` writes no template files into a newer pool.
3. **Runner name.** The by-hand item and `check_item` looked for the machine name `main`. Pool agents register as `<pool>-<slug>`. Now a machine that is a pool (pool folder exists) gets an item with `pool` set; the check looks for `pool_agent_name(pool, repo)` (repo from `gh repo view`; "unknown" if it cannot be read). The item's step is `pool-run`, not a runner install, and it drops off the list when the agent is online.
4. **CI_RUNS_ON.** `pool-run` hard-coded the pool label; `apply`/doctor used the machine's labels only. Now `expected_runs_on()` (pool module) builds the value; `pool-run`, `apply`/by-hand (`delivery_ci_setup.expected_runs_on`) and the doctor hint use it. A pool accepts a superset; a non-pool machine is unchanged (exact).

## What changed
- `delivery_runner_pool.py`: shared rules `plugin_version`, `read/write_pool_version`, `pool_files_state`, `pool_agent_name`, `pool_exists`, `expected_runs_on`, `runs_on_satisfied`, `container_image`. No change to the Dockerfile, supervisor, hooks or sizing.
- `delivery_ci_setup.py`, `delivery_doctor.py`: import and use them.
- Tests: new `tests/test_dl184_pool_doctor_agree.py` (15 tests). Updated the existing `test_dl149_pool_layers.py::test_layer_tools_missing` fake docker to answer `docker inspect` (the old fake answered `docker ps`).
- Docs: pool contract text in `shared-self-hosted-runners.md` (section 4.1 and 7); notes `docs/features/delivery/changes/DL184.md`, `docs/architecture/changes/DL184-pool-doctor-agree.md`.
- Outside the owned list: `docs/features/runner-pool/changes/DL184.md` (patch note). Needed because docs_check rule M1 maps `delivery_runner_pool.py` to the runner-pool spec.

## Tests
- `python3 -m unittest tests.test_dl184_pool_doctor_agree` (in tests/): 15 OK.
- `python3 -m unittest discover -s claude/plugins/delivery/tests`: 1207 run, OK (1 skipped).
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `tools/test_delivery_runner.py` not run locally (session guard: heavy suite, no measurement); CI job "delivery scripts, CI templates, cleanup, prune, change notes" passed.
- New test file is covered: spec-lint runs `unittest discover -s claude/plugins/delivery/tests`; no change to `tools/ci_areas.py` or `.claude/suites.json` was needed.
- `docs_check.py`: only W1 (this report under docs/work/, expected).

## CI
`gh workflow run spec-lint.yml --ref DL184-pool-doctor-agree -f areas=delivery,docs` (run 42927704676). Success: which areas, CI scripts and workflow templates, branch gate and trust rule, setup preflight, train cleanup, change notes enforced and folded, packaged-program smoke test, docs plugin, plugin ledger/recorder/watcher/hooks, artifact pruning, area mapping, runner plan, delivery scripts/CI templates/cleanup/prune/change notes. Skipped: change notes, change notes folded, shard matrix, model profiles, specs/templates, artifact renderer, transcript folds. Failure: docs check, only W1 (this report).

## Follow-ups
- Run `docs_work.py strip` before the join (W1).
- A pool written before this change has no `pool-version.json`; the first `pool-refresh` or `pool-run` adds it. Until then it is compared by files only.

Branch head: see `git log -1` on DL184-pool-doctor-agree (the commit that adds this report).

READY
