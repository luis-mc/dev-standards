# DL220 report

## Base check
Branch reset to origin/main. The Dockerfile has `RUN node --version && corepack --version`. OK.

## Reproduction
Node 22.23.4 tarball (sha256 checked, OK) copied into a root-owned dir `/opt/dl220/node`, its bin first on PATH. Non-root user created with `useradd`, commands run with `runuser -u`.
(A first try under the scratchpad path fell through to the sandbox's own Node, because the test user could not traverse that path. Discarded; redone under /opt.)

- Non-root `corepack enable`, before: `Internal Error: EACCES: permission denied, symlink '../lib/node_modules/corepack/dist/pnpm.js' -> '/opt/dl220/node/bin/pnpm'`.
- Root `corepack enable`: rc=0. Shims pnpm, pnpx, yarn, yarnpkg now exist in bin.
- Non-root `corepack enable`, after: rc=0, no output (no-op). The claim holds.
- Non-root `pnpm --version` in a temp dir with `packageManager: pnpm@9.15.0`: prints `9.15.0` (network worked). A harmless npmrc EACCES warning for root's home appeared in the sandbox only.

## What changed
- Dockerfile: `/opt/node/bin/corepack enable` in the Node RUN step; comment updated; self-check is now `node --version && corepack --version && test -L /opt/node/bin/pnpm` (no pnpm download).
- test_dl215_pool_node.py: dropped the "no corepack enable" assertion.
- New test_dl220_pool_corepack.py: enable after Node install, before any USER, shim self-check, comment text.
- runner-pool spec R5.26 updated; feature note docs/features/runner-pool/changes/DL220.md; change note docs/architecture/changes/DL220-pool-corepack-enable.md (patch, delivery plugin.json).

## Tests
- `python3 -m unittest` on the DL220 and DL215 tests: OK.
- Pool tests (`discover -p "test_*pool*.py"`): 350 tests, OK.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only G1 (stale generated decisions.md) and W1 (this report under docs/work) remain. Both are expected. M1 on the delivery spec was cleared with `Docs: none` in the commit message.
- spec-lint run 43048883609 (areas=delivery): all 10 delivery jobs, area detection and "delivery scripts, CI templates, ..." succeeded; other area jobs and change-note jobs skipped; "docs check" failed on G1 and W1 only.

## Follow-ups
- Run the real image build once on the pool to confirm `test -L` passes (no Docker here).
- G1: decisions.md is stale on main; release fold regenerates.

