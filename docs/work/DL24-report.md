# DL24 report: CIR10 S8, fallback launchers

Branch `DL24-fallback-launchers`. Contract: `docs/proposals/CIR10-delivery-ci.md` on `claude/CIR10-v2-delivery-ci-proposal`, section 8 (owner answers, binding).

## Plan

| Step | What | State |
|---|---|---|
| 1 | Report (this file) | done |
| 2 | `fallback_launch.py`: cloud launcher, hosted launcher, wait measurement, sweep | planned |
| 3 | `fallback_run.py`: what a launched shard runs (claim last, then tests) | planned |
| 4 | Hook in `ci_watch.py` | planned |
| 5 | Hosted workflow `ci-fallback.yml`, hourly routine template | planned |
| 6 | Tests with fakes | planned |
| 7 | Docs: spec section, guide with the test-repository run recipe, change notes | planned |

## Owner answers that shape this step

- Answer 1: the watcher is the session that opened the run, plus an hourly routine. No watchdog job. An unattended fallback can start up to an hour late. The setup and docs say so.
- Answer 5: only runner waits count toward X.
- Answer 6: every run may use the fallback (setting `only_for`, default `all`).
- Answer 7: Windows fallback is hosted Windows for the Windows-only set, on ready PRs.
- Answer 4: caps are optional.

## Interface assumed from DL23 (S7)

DL23 had not pushed `DL23-option4-core` when this was written. The code reaches it only through two small adapters in `fallback_launch.py` (`load_claim`, `load_caps`) so a rebase changes two functions:

- `ci_claim.take(root, remote, sha, shard, who) -> bool` (section 4.3: true = this caller holds the claim).
- `ci_caps.check(root, kind, shards) -> (allowed: bool, reason: str)` and `ci_caps.record(root, kind, shards, minutes)` (section 4.5).

If a module is missing: the claim step fails closed (the shard does not run), and caps count as "none set" (caps are optional, answer 4).

## Shared files (touched outside my own files)

- `claude/plugins/delivery/templates/shared/scripts/delivery/ci_watch.py` (the hook).
- `claude/plugins/delivery/templates/shared/scripts/delivery/CONTRACT.md` (rows for the new files).
- `docs/features/delivery/spec.md` (new subsection in section 13).

## Log
