# DL149 report: pool packaging layer

## What changed
- Dockerfile: build args `POOL_LAYERS` (comma list) and `POOL_APT` (space list); one RUN installs `dotnet-sdk-8.0 wine wine64 xvfb xauth msitools` when `windows-packaging` is in `POOL_LAYERS`, plus the `POOL_APT` names. Off by default. compose.yaml passes both args.
- Base image is ubuntu:24.04: it ships dotnet-sdk-8.0 and wine64 itself, so no Microsoft feed and no i386 architecture. Wine is 64-bit only.
- Config place: `.delivery/config.json` -> `{"pool": {"layers": ["windows-packaging"]}}`; fragment `.delivery/pool.apt` (one name per line, `#` comments, letters/digits/`+ - .` only, no leading `-`). Both are read from the repo checkout by `pool-refresh` and written to the pool `.env` as `POOL_LAYERS` and `POOL_APT`; the rebuild passes them to `docker compose up --build`.
- Bad name or unknown layer: `refused: .delivery/pool.apt line N has "x". A package name may hold only letters, digits, + - . ...` and nothing is changed.
- Busy refusal: `pool-refresh --yes` reads `gh api repos/<repo>/actions/runners` for each repo in the pool's agents.json; any pool runner with busy=true -> `refused: pool runner busy: <name> (<repo>). Wait for the job or use --force.` `--force` rebuilds with `warning: ...`. Unreadable runners also refuse (override with --force).
- Doctor (pool checks, `pool.<name>.*`): `layer-windows-packaging` (wine, xvfb-run, dotnet via `docker run ... command -v`; warn when docker cannot be read), `layers-config` (config vs .env drift), `stray-dockerfile` (Dockerfile under a runners/runner folder, with the fix), `tool-cache` (named volume at /ci-tools in compose.yaml and writable). The new checks live in `delivery_runner_pool.py` (called by the doctor); `delivery_doctor.py` is unchanged, DS202 rust check kept. Also touched: `delivery_ci_setup.py` (`--force` flag only).
- delivery-ci-setup.md: Windows-installer question (suggest yes with `*.wxs`), `.delivery/pool.apt`.

## Commands a project runs after the plugin update
1. Edit `.delivery/config.json`: add `"pool": {"layers": ["windows-packaging"]}` (and optionally create `.delivery/pool.apt`).
2. `python3 <plugin>/scripts/delivery_ci_setup.py pool-refresh --root <project> --pool main` (shows the plan), then the same with `--yes` to write .env and rebuild (add `--force` only if you accept a busy runner failing).
3. `python3 <plugin>/scripts/delivery_doctor.py` to confirm.

## Tests
- `python3 -m unittest test_dl149_pool_layers` (tests/): 13 tests OK.
- `python3 -m unittest test_runner_pool test_dl92_pool_fixes test_pool_supervisor test_dl149_pool_layers`: 194 OK. `test_doctor test_ds202_rust_doctor`: 33 OK.
- `ci_areas.py --branch-advice`: "unreadable diff" -> all areas.
- `docs_check.py`: only W1 (docs/work), as expected.
- No Docker build was run.
- Fix after the first CI run: an absent POOL_LAYERS/POOL_APT key and an empty value count as no change (test_dl103_pool_keep_cap failed before).
- `gh workflow run spec-lint.yml --ref DL149-pool-packaging-layer -f areas=delivery` (run 42681106044): all 10 delivery jobs success (branch gate, train cleanup, CI scripts and templates, setup preflight, artifact pruning, change notes, packaged-program smoke, runner plan, area mapping, ledger/recorder/watcher/hooks) and the aggregate "delivery scripts..." job success. Only `docs check` failed: W1 (docs/work files), expected. The first run (42680533139) failed the ledger job on the bug above.

Branch head: see `git rev-parse origin/DL149-pool-packaging-layer`.

READY
