# DL215 report

Base check: Dockerfile had `ARG NODE_VERSION` (22.23.4). Proceeded.

## What changed
- `Dockerfile`: Node LTS tarball (sha256 checked) now installs for every build to `/opt/node`, kept, `ENV PATH="/opt/node/bin:${PATH}"`. Build check `node --version && corepack --version`. If corepack is missing (Node 25+), npm installs `corepack@${COREPACK_VERSION}` (ARG, 0.34.0; unused on Node 22, version not verified against the registry). No global `corepack enable`. Playwright install-deps still uses this Node.
- Node was before only installed with POOL_BROWSERS=chromium and then deleted.
- New `tests/test_dl215_pool_node.py`; `test_runner_pool.py` old `rm -rf /opt/node-build` assertion now asserts no rm of /opt/node.
- Doctor: it only checks layer tools (LAYER_TOOLS), no base-tools check, so no doctor change (test only).
- Docs: runner-pool spec R5.26 + code map row, feature note DL215, change note `docs/architecture/changes/DL215-pool-node-corepack.md` (patch, delivery plugin.json). Delivery spec M1 handled with `Docs: none` in the commit.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl215_pool_node test_runner_pool test_dl101_pool_browsers test_dl180_wine_tmpdir test_dl149_pool_layers test_pool_supervisor`: pass (200 tests; the one error was my guessed module test_dl182_wine_hash, which does not exist).
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- spec-lint run 1 (43035865502): jobs cancelled mid-run (runner stop), so rerun.
- spec-lint run 2 (43036174367, areas=delivery): all delivery jobs success (area mapping, CI scripts, train cleanup, ledger/recorder/watcher, setup preflight, change notes, smoke test, runner plan, artifact pruning, branch gate, gate job). docs check failed on G1 (stale generated decisions.md, not mine to edit) and W1 (this report under docs/work, by design).
- No Docker build was run; the Dockerfile is untested by a real build.

## Follow-ups
- Build the image once to confirm; confirm runner service sees PATH (it inherits container ENV).

Branch head: see `git rev-parse origin/DL215-pool-node-corepack`.

READY
