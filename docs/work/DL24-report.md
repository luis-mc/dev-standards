# DL24 report: CIR10 S8, fallback launchers

Branch `DL24-fallback-launchers`. Contract: `docs/proposals/CIR10-delivery-ci.md` on `claude/CIR10-v2-delivery-ci-proposal`, section 8 (owner answers, binding).

## Plan

| Step | What | State |
|---|---|---|
| 1 | Report (this file) | done |
| 2 | `fallback_launch.py`: cloud launcher, hosted launcher, wait measurement, sweep | done |
| 3 | `fallback_run.py`: what a launched shard runs (claim last, then tests) | done |
| 4 | Hook in `ci_watch.py` | done |
| 5 | Hosted workflow `ci-fallback.yml`, hourly routine template | done |
| 6 | Tests with fakes | done |
| 7 | Docs: spec section, guide with the test-repository run recipe, change notes | done |

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
- Built: `fallback_launch.py` (wait measurement, once-only reservation branch `ci-fallback/<sha>/<shard>`, cloud launcher through the routine API trigger, hosted launcher through `gh workflow run`, `sweep`, `launch`), `fallback_run.py` (claim last), `ci-fallback.yml`, `routines/ci-fallback-watch.json` (template, not created), the hook in `ci_watch.py` (`--no-fallback`).
- Tests: `python tools/test_delivery_fallback_launch.py` (25 tests, fakes only). Also green: `test_delivery_ci.py`, `test_delivery_cloud.py`, `test_ci_areas.py`, `test_delivery_runner.py`. `ci_areas.py --branch-advice`: "light: test locally only".
- Docs: spec section 13 gains R13.40 to R13.45 (high numbers on purpose, so DL23 does not collide), guide `docs/guides/ci-fallback-test-run.md` (setup, the "up to an hour late" warning, test-repository run recipe), CONTRACT.md rows, two change notes (`DL24-delivery-plugin-fallback.md`, `docs/features/delivery/changes/DL24.md`).
- `docs_check`: two errors, both expected on a task branch. G1: `docs/llms.txt` is stale because of the new guide; generated files are not committed on a task branch, the release regenerates. W1: this report under `docs/work/`; it must be stripped before the join.

## Assumptions to check (not verified against a real service)

- The routine API: POST to `ci.fallback.cloud.fire_url` with bearer token, header `anthropic-beta: experimental-cc-routine-2026-04-01`, body `{"text": ...}`. The URL and header come from my memory of the routines API; check them against the routine's own "API trigger" page before the first real run.
- Job to shard match: the shard `id` or `context` appears in the job name. A project whose job names differ needs that changed.
- Hosted workflow runs on `ref` (default `main`) because the workflow file must exist on that ref.
- DL23 interface (see above): `ci_claim.take`, optional `ci_claim.post_status`, `ci_caps.check`, `ci_caps.record`. Missing claim module: fail closed. Missing caps module: no caps.

## Not done / for others

- `cleanup.py` should delete `ci-fallback/*` branches for finished commits next to `ci-claim/*` (a file I do not own).
- The doctor and the setup command (S6) should write `ci.fallback` and print the "up to an hour late" warning and the by-hand steps; the guide has the text.
- No real run was made. The owner starts the test-repository recipe by hand.
- DL23 branch was not on the remote when this was written; I did not rebase on it.
