# DL188 report

Base check: `git fetch origin main && git checkout -B DL188-doctor-tools origin/main`; plugin.json version 1.25.0 (ok).

## What changed
1. Cached tools: `ci_tool.py` has a new `cached_tool(name, plat, exe, pin_path)`. It gives the path `tool` would use (file kind, archive `unpacked-<plat>/<bin_dir>`, crate root) and downloads nothing. The doctor loads the plugin's own ci_tool.py and asks it (`_cached`), then PATH. Covers Windows (`LLVM-x/bin`) and Linux shapes.
2. Pins: `_pin_problem` accepts a flat `sha256` (string or map) or `platforms` entries. Needed platforms: this host, plus `windows_x64` for Windows targets and `linux_x64` for Linux targets. The finding names the missing platform, e.g. `zig (platform windows_x64)`.
3. Fix text: `ci_tool.py ensure zig|llvm` is now `ci_tool.py tool zig|llvm`. A test checks every `ci_tool.py <sub>` in the doctor against ci_tool's `add_parser` names.
4. New check row `scripts`, item `ci.scripts-current` (warn only). It reuses `delivery_ci_install.plan(..., "update")`: stale or missing files under scripts/delivery warn with the files and `delivery_ci_install.py update --track X` (use `--dry-run` first). A file listed under `keep` in `scripts/delivery/ci-install.json` counts as ok and is named.
5. Wait: `_wait_min(cfg)` reads `ci.wait_min` (10 when unset or bad); the second-machine note and runner steps use it.

Not touched: delivery_ci_setup.py, delivery_runner_pool.py, workflows, .gitleaks.toml, docs/features/delivery/spec.md. `tools/ci_areas.py` maps `claude/plugins/delivery/.*` to the delivery area, which runs the plugin tests, so the new test is covered; no suites.json change needed.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl188_doctor_tools test_ds202_rust_doctor test_doctor test_dl184_pool_doctor_agree test_ci_options test_ci_setup test_machine test_dl173_compat`: 193 tests OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `python3 claude/plugins/docs/scripts/docs_check.py`: M1 on delivery-speed (answered by `Docs: none` in the commit message, as the brief allows); W1 for this report (expected, strip before the join); T2 warnings only.
- `gh workflow run spec-lint.yml --ref DL188-doctor-tools -f areas=delivery,docs` (run 42933823569): all jobs ended.
  - success: which areas, train cleanup, branch gate and trust rule, ledger/recorder/watcher/hooks, change notes enforced and folded, runner plan, area mapping, docs plugin, artifact pruning, packaged-program smoke test, setup preflight, CI scripts and workflow templates, delivery scripts/CI templates/cleanup/prune/change notes.
  - skipped (not in the areas): change notes folded, change notes, specs/templates/AUTHSPEC, transcript folds, artifact renderer, model profiles, branch gate shard matrix.
  - failure: docs check, only for W1 (this report under docs/work/, D9). Not a reason for NOT READY.

## Spec text for the join (docs/features/delivery/spec.md, owned by DL187)
New doctor check ID: `ci.scripts-current` (new, row `scripts`, warn only; not an M-level failure).
- The doctor finds Zig and LLVM in the ci_tool cache at the path `ci_tool.py` uses, then on PATH.
- The doctor accepts a flat `sha256` or per-platform `platforms` pins in tools.json, and names the platform that has no pin.
- Doctor fix text names only real `ci_tool.py` subcommands (`fetch`, `gitleaks`, `tool`).
- `ci.scripts-current` WARNS when a `scripts/delivery` file is older than, or missing from, the plugin templates; it names the files and `delivery_ci_install.py update`. A file in `ci-install.json` `keep` is ok.
- The doctor shows and uses `ci.wait_min` (10 when unset).

## Follow-ups
- delivery_ci_setup.py `check_by_hand` and delivery_config.py defaults still print the 10 min example when called without a value; callers outside the doctor should pass `ci.wait_min`.
- Projects with a ci_tool.py older than this one still work: the doctor uses the plugin's copy.

Branch head SHA: see `git rev-parse origin/DL188-doctor-tools` (the report commit follows the code commit).

READY
