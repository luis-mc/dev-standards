# DL20 report: CIR10 S4, inputs key and pass records

Task DL20, branch `DL20-pass-records`, 3 Nov 2026. Contract: CIR10 proposal sections 2.1 (L4, L5) and 8.

## Plan

1. Module `pass_records.py`: inputs key, records branch, lookup, write, cleanup.
2. Hook it into `cloud_shard.py` (skip on a pass record) and `cleanup.py` (drop a deleted branch's records).
3. Fake-remote tests in `tools/test_delivery_records.py`.
4. Spec text, `CONTRACT.md`, change notes.

## Progress

- Step 0: branch created from `origin/main`; contract read. No `CLAUDE.md` exists in this repository; `AGENTS.md` was read.
