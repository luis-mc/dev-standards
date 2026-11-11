# DL199 report

Base: origin/main 85c5d72 (LAYER_TOOLS present).

## What changed
- `delivery_runner_pool.py`: `pool_container_running` and `_probe_layer_tool`. A running container is probed with `docker exec`; with none running, `docker run` on the image. Exit 0 = ok, 1 = missing (fail), anything else or timeout = warn `cannot probe` naming the exit. Check id and ok text unchanged.
- New `tests/test_dl199_doctor_layer_exec.py` (5 tests).
- runner-pool spec R5.17 text; feature note `features/runner-pool/changes/DL199.md`; change note `docs/architecture/changes/DL199-doctor-layer-exec.md`.

## Tests
- `python3 -m unittest test_dl199_doctor_layer_exec test_dl149_pool_layers test_dl184_pool_doctor_agree` (in tests/): 33 ok.
- `python3 -m unittest test_runner_pool test_doctor test_dl188_doctor_tools test_dl194_pool_tool_cache test_dl92_pool_fixes`: 211 ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- spec-lint run 42994293586 (areas delivery,docs): every delivery job and docs plugin success; skipped jobs skipped; `docs check` failed with G1, M1, W1 (below).

## Follow-ups
- G1: docs/architecture/decisions.md stale; generated, the release fold rebuilds it. Not committed.
- W1: this report is under docs/work/; strip before the join (expected).
- M1: delivery spec mapped to the pool script; no change needed there, the commit now says `Docs: none`.
- `sh` returns no stderr, so the warn names the docker exit code, not the docker message.
