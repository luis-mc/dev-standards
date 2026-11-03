# DL19 report: CIR10 step S3, learning L3

Task: shard-table guard, timings balance for all suites, shard sizing and memory limit in `cloud_shard.py`.
Contract: `docs/proposals/CIR10-delivery-ci.md` on `claude/CIR10-v2-delivery-ci-proposal`, rows L3 and S3.

## Plan

1. `shard_table.py` (new): resolves a shard table to files per shard. Suites list test globs. A shard names a suite and either a balanced `part` ("K/N") or explicit `members` globs.
2. `shard_guard.py` (new): fails when a test file is in no shard or in two shards, when a suite's parts are incomplete, and when a shard's sizing or estimated time breaks its limits.
3. `shard_balance.py`: `--table` and `--shard-id` so every suite is balanced from its timings, not only e2e.
4. `cloud_shard.py`: sizing from the table (workers, cpus, memory, timeout), `{files}` expansion, peak memory measured and checked against the limit.
5. Tests in `tools/test_shard_guard.py`, wired into spec-lint beside `test_ci_speedups.py`? No: the workflow is a shared file, so it is listed below for the orchestrator.
6. CONTRACT.md section, example table, change note.

## Status

Done and pushed on `DL19-shard-table-guard`:

- `shard_table.py` (new): suites, `part "K/N"` (balanced by timings, any suite), `members` (explicit), per OS, `discover` globs for files no suite takes.
- `shard_guard.py` (new): `check` fails for a file in no shard, a file in two shards, a missing or repeated part, a suite with no shard or no files, a stale `members` glob, a `size` over `limits`, more workers than cpus, and an estimate over the timeout.
- `shard_balance.py`: `--table T --shard-id ID` prints one shard's files, so every suite is cut by timings.
- `cloud_shard.py`: `size` from the table (filled from `limits`), env `CI_SHARD_WORKERS/CPUS/MEMORY_GIB`, `{files}` and `{workers}` in commands, `--timeout-min` still wins, `peak_memory_gib` read after each command, a peak over `memory_gib` is a failure, a size over `limits` is an `error` with nothing run. The result gets `size` and `peak_memory_gib`.
- `CONTRACT.md` (section "Suites, parts, sizes and the guard"), `ci-shards.example.json`, tests in `tools/test_shard_guard.py` (19 cases, includes three guard mutants).
- Change notes: `docs/architecture/changes/DL19-shard-table-guard.md` (plugin) and `docs/features/delivery/changes/DL19.md` (feature).

## Proof

- Guard fails for a file in no shard and for a file in two shards (several variants each); mutants of those rules pass the broken project and are caught.
- The sample project in the test (6 unit, 4 e2e, 2 budget files; limits 4 cpus, 8 GiB, 15 min) passes the guard and every shard's estimate is under its timeout.
- Ran: `python3 -m unittest test_shard_guard` (19 ok) and `test_delivery_cloud.ShardTests` (6 ok) from `tools/`.
- Not run locally: `test_delivery_cloud.py` in full and `test_ci_speedups.py`; both are declared heavy and the session guard refuses them. `ci_areas.py --branch-advice` says heavy: run `spec-lint.yml` with areas `specs,delivery,artifacts,profiles,transcript-folds,docs`. See the PR for whether that was started.
- `docs_check`: no errors except W1 (this report under `docs/work/`, expected on an agent branch), plus two T2 staleness warnings on delivery specs (S11 rewrites them).

## Shared files touched

- `claude/plugins/delivery/templates/shared/scripts/delivery/CONTRACT.md` (one new subsection, one file-table row, one test-list entry). Likely conflict zone with S4, S5, S7, S11.
- `claude/plugins/delivery/templates/shared/scripts/delivery/cloud_shard.py` (S4, S7 may also edit; my edits: imports, `run_command` signature gets `env`, `run_shard` sizing block, result keys).
- `claude/plugins/delivery/templates/shared/scripts/delivery/shard_balance.py` (CLI only).
- `claude/plugins/delivery/templates/shared/scripts/delivery/ci-shards.example.json`.
- Not touched, left to S11: `docs/features/delivery/spec.md` section 13 needs a sentence for the suites, the guard and sizing (R13.2 and R13.6). `.github/workflows/spec-lint.yml` should run `tools/test_shard_guard.py` beside `test_ci_speedups.py` (workflow is shared; not edited here).

## Open points

- `ru_maxrss` of children is the largest single process, not the sum over a process tree. A suite with many parallel workers can use more than the number read. The memory limit is therefore a floor check. Say so in the setup text.
- The estimate divides recorded seconds by `workers`. It ignores start-up. Timings from one worker count are not exact for another.
