# DL180 report (final)

## Base check
`git fetch origin main && git checkout -B DL180-wine-tmpdir origin/main`; `git merge-base --is-ancestor 8d7358b1 HEAD` rc=0 (HEAD 8d7358b).

## What changed
- Dockerfile: one new RUN block after the windows-packaging install. Writes `/usr/local/bin/<tool>` wrappers (unset TMPDIR, exec /usr/bin/<tool>) for wine, wine64, wine-stable, wineboot, wineserver, winecfg, msiexec when present. Self-check: wine on PATH is the wrapper.
- Test `claude/plugins/delivery/tests/test_dl180_wine_tmpdir.py` (6 tests, includes a run of the wrapper on Linux).
- Notes: `docs/features/runner-pool/changes/DL180.md`, `docs/architecture/changes/DL180-wine-tmpdir.md`.

## Tests
- test_dl180_wine_tmpdir: 6 tests OK
- test_dl149_pool_layers: 13 tests OK
- test_dl167_pool_llvm: 5 tests OK

## Spec text for the join
Runner pool: the image wraps each Wine entry tool (wine, wine64, wineboot, wineserver, winecfg, msiexec) in `/usr/local/bin` with a script that unsets `TMPDIR` and runs the real tool. Wine aborts with `free(): invalid pointer` when `TMPDIR` is set. The pool still sets `TMPDIR` for every other tool. The image build fails if `wine` on PATH is not the wrapper.

## CI
spec-lint run 42904606928 (areas=delivery,docs), first run: failure only in `docs check`: G1 (decisions.md stale, generated, not touched by this branch), M1 (delivery spec mapped to the Dockerfile; fixed by `Docs: none` in the next commit message, the runner-pool note covers the change), W1 (this report, expected). All other jobs success; skipped: change notes folded, change notes, shard job, specs/templates, artifact renderer, transcript folds, model profiles.
Rerun below.
