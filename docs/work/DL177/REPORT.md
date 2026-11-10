# DL177 report

## Base check
`git merge-base --is-ancestor abcda856 HEAD` succeeded (HEAD abcda85).

## What changed
- delivery_runner_pool.py: Probe.wsl_vm_parts/wsl_vm_gib (max of working set, private bytes), Probe.docker_run (Windows docker CLI first, `wsl docker` fallback) used by docker_cpus and container_gib, detect_host (VM floored at container use, host-load sample, decided-by), measured_sizing inputs, memory-per-CPU message with nearest passing sizes. detect_containers and Executor already try the plain CLI; no other `wsl docker` call needed a change.
- delivery_ci_setup.py (NOT in the owns list, but the Sizing inputs line is printed there): one added line with VM figures, host-load state and what decided.
- Host-load file holds one sample (mem %, at), not a series; it is used as that one sample, ignored when over 60 s old.
- Spec R5.22 to R5.24, feature note, change note.

## Tests
- Base check: `git merge-base --is-ancestor abcda856 HEAD` passed.
- `python3 -m unittest` in claude/plugins/delivery/tests: test_dl177_pool_measure (17), test_dl176_pool_resize (23), test_runner_pool (149), test_dl103_pool_keep_cap (17), test_dl101_pool_browsers (16), test_dl149_pool_layers (13), test_ci_setup (29): all OK.
- `docs_check.py`: two errors left. G1 (decisions.md stale) is also on origin/main. W1 (docs/work report) is the expected rule for this branch.

## CI (spec-lint run 42882578407, areas=delivery,docs, code head 344120e)
success: which areas, change notes enforced and folded, train cleanup, runner plan, CI scripts and workflow templates, branch gate and trust rule, packaged-program smoke test, artifact pruning, plugin ledger/recorder/watcher/hooks, docs plugin, area mapping, setup preflight, delivery scripts/CI templates/cleanup/prune/change notes (rollup).
skipped: change notes, change notes folded, model profiles, artifact renderer, transcript folds plugin, branch gate shard, specs/templates/AUTHSPEC.
failure: docs check (W1 for this report, G1 stale decisions.md as on main; no other error).

## Other
- Touched delivery_ci_setup.py (not owned) for the Sizing inputs line.
- Branch head: code commit 344120e; the report commit follows it.

READY
