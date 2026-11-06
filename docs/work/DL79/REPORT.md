# DL79 report

1. Memory per CPU: `MIN_GIB_PER_CPU = 1.5`, `cap_mem_cpus()`, used in `sizing` and again in `do_pool_files`. Sizing output has `cpus_text`; the pool-files step text shows it.
2. cpuset: `.env` gets `POOL_CPUSET=0-<N-1>`; compose has `cpuset: ${POOL_CPUSET:-}`. NOT tested against Docker (no Docker allowed). I kept the empty-default form, which I believe the engine treats as unset. If compose rejects it, change to omit the key when unset.
3. Hint: `.env` gets `POOL_CPUS_INT`; compose sets `CI_MAX_PARALLEL: ${POOL_CPUS_INT:-1}`. Spec documents vitest and turbo use.
4. Doctor: new `mem-per-cpu` check, warn under 1.0 GiB per CPU, names both values and the fix.
5. Tests: new `DL79MemPerCpuTests`. One old test (`test_pool_files_cap_follows_docker`) used 6 GiB; raised to 40 so it still tests the Docker cap.

## Commands
- `cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool`: 134 tests, OK.
- `python3 tools/ci_areas.py --branch-advice`: "heavy: unreadable diff", advises `gh workflow run spec-lint.yml ...`. Not run: no gh, and it is not light.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.

Docs: change note `docs/architecture/changes/DL79-delivery.md`, feature note `docs/features/delivery/changes/DL79.md`, spec text updated.

Branch head SHA: see the last commit on DL79-pool-mem-per-cpu.

READY
