# DL342 / DL343 report

Branch: DL342-pool-cache-kvm. Ships in RELEASE-138.

## Root cause (DL342)

Confirmed by reading `rust_ci.py`. `target_cache_env()` reads `RUST_TARGET_CAP_GB` (default 40) and calls
`prune_target_cache()`. That function never removes the current key or the newest other key, and only removes whole
other keys. One key directory (incremental and deps leftovers) had no ceiling, so it grew without bound. This is
the cause of the 320 GB cache. On Windows `key_in_use()` also returned True for every key (no fcntl), so nothing
was ever pruned there.

## What changed

- `rust_ci.py`: new `enforce_cap()` after the prune. Newest other key goes if still over; an oversized current key
  loses `incremental/`, then all content, unless in use. One stderr line says what and why. `key_in_use()` now has a
  Windows check (msvcrt byte lock; unclear counts as in use).
- `delivery_runner_pool.py`: per-runner sweep (`sweep_runner_cache`, `sweep_pool_caches`, `tool_cache_cap_gb`, default
  30, `tool_cache_cap_gb` in machine.json), run at pool start and by new action `cache-sweep`. Linux agents are swept
  inside the pool container with `docker exec`, Windows services on the local disk. Busy or unreadable runners are skipped.
  Doctor checks `cache-cap` and `cache-disk` (<10% free). `ensure_kvm()` runs before compose up in `do_pool_up`,
  the cap recreate and `drain_and_recreate` (pool-refresh); `kvm-wslconfig` doctor check.
- `delivery_ci_setup.py`: prints the `.wslconfig` warning in pool-plan and pool-run.
- Docs: spec R5.53 to R5.57, failure modes, test rows, feature notes DL342.md and DL343.md, plugin notes.

## Not done

- `runner_job_done.*` is not in the owned files, so the job-end trigger is the `cache-sweep` action (a hook can call it)
  plus pool start. No hook was edited.
- `delivery_doctor.py` was not edited: it already takes the pool doctor's checks.
- The Windows msvcrt lock and the real modprobe run only on real machines; tests mock them.

## Tests

- `python3 -m unittest test_dl342_cache_cap test_dl343_kvm_autoload` (in claude/plugins/delivery/tests): 25 tests, OK.
- Plus existing: test_dl329_rust_target_link, test_ds200_rust_ci, test_dl295_rust_scope, test_dl341_pool_all_oses,
  test_dl274_kvm_layers, test_dl281_vm_check, test_runner_pool, test_dl289_refresh_drain, test_dl310_windows_runner,
  test_dl339_hook_python, test_doctor: 364 tests together, OK (1 skipped).
- `docs_check.py`: only W1 (docs/work on branch), which is expected; strip before the join.
- `ci_areas.py --branch-advice`: heavy area delivery, run `gh workflow run spec-lint.yml --ref DL342-pool-cache-kvm -f areas=delivery` (not run here).


Branch head (before this line was added): 4aae564adf1cbda8f0cf19d19b1cc813ff3b98f3

READY
