# DL39 report: runner hook fixes

## Files changed
- Gate: `scripts/runner_load_gate.py`, `scripts/machine_slots.py` (`shard_from_env`, ident), `scripts/delivery_doctor.py`.
- F1: removed `runner_load_gate.cmd` and `runner_job_done.cmd`. Setup text (`delivery_ci_setup.py`), pool printed steps (`delivery_runner_pool.py`), README, guide, specs name the `.ps1` wrappers. Doctor `machine.hooks` FAILS a `.cmd` hook and names the fix.
- F2: shard = `DELIVERY_SHARD` if the hook sees it, else `GITHUB_JOB`. Template jobs already had key = shard; the only mismatch was the `e2e-shard` matrix job (now `e2e-shard`; legs share the key). A test now checks every template job's `DELIVERY_SHARD` equals its key. The fallback side (`ci_fallback.py`, `ci_watch.py`, `fallback_launch.py`) builds refs from the shard-table `id`, so the rule is: the job key equals the shard id in `ci-shards.json`. No code change was needed there.
- F3: `Marker` loads `ci_fallback.py` from the checkout, else the plugin copy (found relative to the script). It logs one line for each skip: no sha, no shard, no checkout, no module, failed push.
- F4: doctor item `machine.push:<runner>`: dry-run push of a `ci-wait/doctor-check/probe` ref from the kept checkout (`DELIVERY_MARKER_ROOT` in the runner `.env`, else `_work/*/*`). WARNs with the fix. It reads and prints no token. New guide step 10 and a Security section.
- Docs: `docs/features/delivery/spec.md` (R13.64, R13.67), `shared-self-hosted-runners.md`, `docs/guides/set-up-ci.md`; notes `docs/features/delivery/changes/DL39.md` and `docs/architecture/changes/DL39-runner-hook-fixes.md`.
- Tests: `tests/test_machine.py` (precedence, plugin copy, skip logs, no `.cmd`, doctor `.cmd` and push probe).

## Decisions and open points
- `runner_job_done.py` `empty_folder` deletes everything in the workspace, `.git` too (a test asserts an empty folder). The live `.git` only stayed because Windows could not remove read-only pack files. Do not rely on it: on a clean machine set `DELIVERY_MARKER_ROOT` in the runner `.env`. Left as is, not in DL39 scope; a follow-up could keep `.git` on purpose.
- The push probe runs as the doctor's account, which may differ from the runner account. The detail says so only in the fix text.
- `delivery_runner_pool.py` and `delivery_ci_setup.py` had no .cmd hook lines; I made the printed hook steps name the `.ps1` wrappers.
- Not touched: `ci_runs.py`, renderer, claude-setup skill.

## Ran
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests`: 524 tests OK.
- `tools/test_delivery_hooks.py` 55 passed; `tools/test_delivery_fallback.py` OK; `tools/test_delivery_runner.py` all passed.
- `tools/ci_areas.py --branch-advice`: light, test locally only.
- `docs_check.py`: only W1 (this report, expected, stays on the branch) and two warnings (M1 README code root, T2 test-cost spec, both pre-existing in kind).
- No mutation passes, no Docker. No UI change.

READY
