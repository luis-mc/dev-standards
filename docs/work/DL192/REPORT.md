# DL192 report

Base: `git fetch origin DS228-integration && git checkout -B ...` gave a69b3d0. `test_dl190_pool_integration_job.py` exists: base check passed.

## What changed per gap
1. PATH: `export PATH="$HOME/.cargo/bin:$PATH"` now comes before the `GITHUB_PATH` line in all three ci.yml toolchain steps and the one package.yml step. The `GITHUB_PATH` line stays.
2. ci.yml: a `targets` step (cargo metadata, the DL187 pattern) gates `cargo run --bin codegen` and `cargo test --test contract`. A skipped target logs a "Skipped ..." step. package.yml copies the binaries named in `smoke.json` `smoke.binaries` (also the Windows `.exe`), not `app`. An empty list copies nothing and says so; the uploads use `if-no-files-found: ignore`.
3. Windows deferred: `delivery_ci_install.py` (rust track only) skips `windows-msi-check.yml` and `package-windows.yml` unless `ci.options.windows` in `.delivery/config.json` holds a CI option.
   - Config value chosen: absent (not chosen) or `deferred` means deferred. Reason: `ci.options` already holds only a chosen option per OS (`ci_options()` drops other values), so "not chosen" needs no new key.
   - package.yml: the cargo-xwin tool install, build and upload run only when repository variable `CI_WINDOWS` is `on`.
   - Turning on: `delivery_ci.py set`, set `CI_WINDOWS=on`, run `install` again. No hand edits.
   - The skip list reuses the ci-install.json "skipped" label in the output. Other tracks are unchanged.

## Tests
- `python3 -m unittest test_dl192_rust_templates` (in claude/plugins/delivery/tests): 8 passed.
- All delivery plugin tests (`unittest discover`): 1278 ran, OK (1 skipped). No older test pinned the old text.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `tools/ci_areas.py --branch-advice` said `areas=delivery,profiles`; I ran `delivery,docs,profiles` (run 42937949994). The new test is under the delivery area.
- `docs_check.py`: only W1 (docs/work, expected) plus T2 warnings.

## spec-lint run 42937949994 (every job ended)
success: areas, CI scripts and workflow templates, setup preflight, branch gate and trust rule, artifact pruning, docs plugin, runner plan, change notes enforced and folded, train cleanup, packaged-program smoke test, area mapping, plugin ledger/recorder/watcher/hooks, model profiles, delivery scripts/CI templates/cleanup/prune/change notes.
skipped: change notes folded, change notes, specs/templates/AUTHSPEC, artifact renderer, branch gate shard matrix, transcript folds.
failure: docs check, only W1 (this report under docs/work; stripped before the join).

## Follow-ups
- delivery_doctor.py and ci_tool.py untouched, as told. The doctor may warn about a missing Windows workflow while Windows is deferred.
- artifact-prune.yml still lists package-windows; harmless when the file is absent.
- Not run: real GitHub run of a rust project with the new ci.yml.

Branch head: see `git rev-parse` of the pushed branch (the commit after this report).
READY
