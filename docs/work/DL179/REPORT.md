# DL179 report

Base check: `git fetch origin main && git checkout -B DL179-pool-wine-prefix origin/main`, then `git merge-base --is-ancestor 8d7358b1 HEAD` succeeded (base 8d7358b).

## What changed
- `pool_supervisor.py`: `prepare_wine_prefix` (runuser as the agent user, `WINEPREFIX=/agents/<slug>/.wine`, `WINEDEBUG=-all`, `timeout 180`, `xvfb-run -a wineboot --init; wineserver -w`; skipped when system.reg exists; failure logged, never raised; nothing when wine is not on PATH). It runs in the `ensure` chain before each runner start and always returns True. `agent_env(agent)` sets `POOL_WINE_PREFIX` when wine is on PATH.
- Runner-pool spec: R5.17, R5.18. Feature note `docs/features/runner-pool/changes/DL179.md`. Change note `docs/architecture/changes/DL179-wine-prefix.md`.
- Tests: `claude/plugins/delivery/tests/test_dl179_wine_prefix.py` (9 tests).
- Dockerfile and compose.yaml: not changed.

## Step 3 (why the first wineboot crashes)
Not found, and I cannot be sure. No Docker was allowed, so I could not reproduce it. Candidates that I did not act on: `--no-install-recommends` skips `fonts-wine` and other recommended packages; a prefix created inside a job may lack a usable HOME or a clean display. Steps 1-2 avoid a first boot inside a job. If the boot in step 1 also crashes, the log line `wine prefix for <user> failed` will show it, and the next step is to test `fonts-wine` and `WINEARCH=win64` in the layer.

## Tests
- `python3 -m unittest test_dl179_wine_prefix` (in claude/plugins/delivery/tests): OK, 9 tests
- test_pool_supervisor: OK (9); test_dl167_pool_llvm: OK (5); test_dl149_pool_layers: OK (13); test_dl92_pool_fixes: OK (23); test_runner_pool: OK (149)
- `docs_check.py`: only G1 (generated decisions.md stale) and W1 (docs/work on branch); neither blocks.
- spec-lint run 42904111343 (areas=delivery,docs), all jobs ended: success for every selected job (areas, 10 delivery jobs, docs plugin, delivery scripts); skipped: change notes, change notes folded, sharded gate, model profiles, transcript folds, specs/templates, artifact renderer; failure: `docs check` with only G1 and W1.

Code head before this report commit: see `git log` on the branch.

READY
