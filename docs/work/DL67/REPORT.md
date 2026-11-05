# DL67 report: pool browsers option

## What changed
1. `browsers` setting (none default, chromium): `plan --browsers` in `delivery_runner_pool.py`. The script reads no pool section in `.delivery/config.json`, so no second config place was added. Written to the pool `.env` as `POOL_BROWSERS`; `compose.yaml` passes it as a build arg; `pool-up` also sets it in the build environment. Dockerfile: `ARG POOL_BROWSERS=none`, one `ARG PLAYWRIGHT_VERSION=1.49.1`, and a conditional `RUN` that installs nodejs/npm, runs `npx -y playwright@${PLAYWRIGHT_VERSION} install-deps chromium` as root, and cleans apt lists. Default image is unchanged.
2. Plan step text (`pool-files`) says whether the image has the Chromium libraries and the 300-400 MB size.
3. The CI_RUNS_ON workflow check also lists workflows with `sudo`, `apt-get`, `apt install`, `--with-deps`, `install-deps`. The step still passes.
4. Tests: new `BrowsersTests` (env and build arg, default none, pool-up env, plan text, Dockerfile line, warning).
Docs: spec section 4.1 and 6.3 updated; change notes `docs/architecture/changes/DL67-delivery.md` and `docs/features/delivery/changes/DL67.md`.

## Commands
- `cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool`: OK, 110 tests.
- `python3 tools/ci_areas.py --branch-advice`: "heavy: unreadable diff, run spec-lint workflow for all areas" (needs `gh`, not available here; not run).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.
- No Docker build was run.

