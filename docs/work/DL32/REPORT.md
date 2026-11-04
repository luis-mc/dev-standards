# DL32 report: machine layer (agent A)

Branch `DL32-machine-layer`, built on `origin/main`. Pushed only that branch.

## Files changed
New (plugin `claude/plugins/delivery`):
- `scripts/machine_slots.py`: machine dir, machine config read and write, slots (create-new locks), queue tickets and order, stale freeing, slot log.
- `scripts/runner_job_done.py` (+ `.sh`, `.cmd`, `.ps1`): job-completed hook.
- `tests/test_machine.py`: 54 tests.

Changed:
- `scripts/load.py`: machine config first (old file as fallback), project can only lower, `--write`, `host-load.json`, cgroup v2 figures, worse of host and container.
- `scripts/runner_load_gate.py`: ticket, queue, slot, ci-wait marker, claim-lost exit 3; the old load-only gate when no machine layer exists.
- `scripts/load_guard.py`, `hook_pre_tool.py`, `hook_post_tool.py`: DL-91 local heavy limit.
- `scripts/delivery_ci.py` (`slots`), `delivery_doctor.py` (`machine` check, `clean-work`), `delivery_config.py` (accessors), `references/config-schema.json` (`local_heavy`, `ci.fallback.cloud_ci_sessions`).
- `templates/shared/scripts/delivery/ci_fallback.py` (wait marker, `shard_wait_minutes`, `held`, cloud session count and limit), `fallback_launch.py` (cloud limit, wait marker).
- `DELIVERY_SHARD` on every job of the workflow templates (dotnet, go, rust, ts, shared, except `ci-fallback.yml`).
- `hooks/hooks.json`: PostToolUse and PostToolUseFailure matchers now include `PowerShell` and `Workflow` (needed to end a heavy call). Not on the contract's file list.
- Tests: `tests/_helpers.py` (isolated machine and heavy folders), `tests/test_load.py`, `tests/test_doctor.py`, `tools/test_delivery_fallback.py`, `tools/test_delivery_fallback_launch.py`.
- Docs: `docs/features/delivery/spec.md` (R13.60 to R13.67, failure modes), `docs/architecture/DELIVERYSPEC.md` (DL-79 changed, DL-90, DL-91, load_limits line), `claude/plugins/delivery/README.md` (own subsection).
- Notes: `docs/architecture/changes/DL32-machine-layer.md` (DELIVERYSPEC and delivery `plugin.json`, minor), `docs/features/delivery/changes/DL32.md` (minor), `docs/features/delivery-speed/changes/DL32.md` (patch, because the touched templates map to that spec).

## Decisions the contract did not settle
1. **Project limits can only lower** (D21 text in section 3.1). Three old tests expected a project to raise a limit; I changed them.
2. **No machine layer, no new behaviour.** If neither `machine.json` nor `slots/` exists, the gate is the old DL-79 load gate. If the machine folder cannot be written it falls back to that too, and says so.
3. **Holder process.** The lock stores the parent of the hook (the runner worker). On Windows a `cmd`/`powershell` parent is skipped. `DELIVERY_HOLDER_PID` overrides. A dead pid frees a slot only when the lock's host name equals this host (a pool container has its own pid space).
4. **Lock content.** Locks are made by hard-linking a finished temp file (complete content at once); `O_EXCL` if links are refused. Slot and queue folders are made mode 0777 (no sticky bit) so runner accounts can free each other's stale slots.
5. **Slot log lines.** One `queued_at` + `slot_at` line at take, one `released_at` line at free (joined by repo, run, attempt, job).
6. **ci-wait marker needs a git checkout.** The job-started hook runs before checkout. It uses `DELIVERY_MARKER_ROOT`, else `GITHUB_WORKSPACE` if it has `.git` (a persistent runner keeps the last checkout), and loads `scripts/delivery/ci_fallback.py` from it. With none, no marker is written and the log says so. Whether the job's `env:` (DELIVERY_SHARD) reaches the hook was not verified against a real runner.
7. **Claim lost** is checked once, right after the slot is taken (any claim for the shard, `ci_fallback.py held` exits 3). The hook returns 3 and frees the slot.
8. **Cloud session count** = `ci-claim` branches whose holder contains "cloud", with no `ci-posted`, younger than 3 hours (so a dead session stops counting). The limit is read from `machine.json` by path (the launcher is a project script and cannot import the plugin); `ci.fallback.cloud_ci_sessions` may lower it. A hosted fallback is not limited.
9. **Local heavy** state lives in `local-heavy/` of the machine folder when writable, else `~/.claude/luismc-delivery-local-heavy`. A call is counted only after every other pre-tool rule allowed it. Check id `DL-91`. The Agent tool is counted from the ledger only.
10. **Doctor `machine` check** is skipped (ok) when no OS is Option 1 and no machine folder exists. The disk warning starts at 20 GB. `clean-work` decides "job running" from slot holders by runner name.
11. Pool checks: `delivery_runner_pool.doctor_checks(root)` is called when the module imports; today it shows `skip`.

## Not verified here
- Section 9 risk 1 (Windows and pool racing on a bind mount, 1,000 rounds): only the Linux two-process race (2 x 500 rounds) ran. If a bind mount ever loses a race, slots need the lock service from the contract.
- Section 9 risk 2 (`NETWORK SERVICE` write rights): needs a Windows host; the setup (agent B) grants the rights.
- No real runner, no real GitHub, no Docker.

## Ran
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests`: 449 tests, OK.
- `tools/` delivery tests (`test_delivery_*.py`): 96 tests, OK. `test_ci_areas`, `test_spec_check`: OK.
- `docs_index.py build` + `docs_check.py`: only the expected W1 error for `docs/work/DL32/REPORT.md` (branch only). Generated files restored with `git checkout`.
- `change_notes.py check`: ok.
- `tools/ci_areas.py --branch-advice` says to run the heavy `spec-lint.yml` on the branch with `areas=delivery`; not run (no Docker, no GitHub Actions access from here).
