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

- [ ] S-a shard_table + shard_guard
- [ ] S-b shard_balance table mode
- [ ] S-c cloud_shard sizing and memory
- [ ] S-d tests, docs, notes

## Shared files touched

(filled in at the end)
