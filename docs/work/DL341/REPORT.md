# DL341 report: the pool covers all OSes (D298)

Branch: DL341-pool-all-oses (from origin/DL338-integration). Code head before this report commit: 4893836b494ace56f453d783249e7adc30c40abf. The report commit sits on top of it.

## Files

- claude/plugins/delivery/scripts/delivery_runner_pool.py: registry helpers (entry os/kind, upsert, drop, read, write), Windows pool labels, `windows_runs_on` with pool and route, plan steps `win-labels`, `registry`, `registry-drop`, executors `add-labels`, `registry-windows`, `registry-drop`, `windows-runner-remove`, doctor `registry_checks`, container-only filtering of the agent list.
- claude/plugins/delivery/scripts/pool_status.py: new, read only, text or `--json`.
- claude/plugins/delivery/scripts/delivery_ci_setup.py: `pool-status` and `pool-remove --runner NAME [--yes]`.
- claude/plugins/delivery/scripts/delivery_doctor.py: warns when `CI_RUNS_ON_WINDOWS` has no pool label.
- claude/plugins/delivery/templates/runner-pool/pool_agents.py, pool_supervisor.py: skip `kind: service` entries (the supervisor would not have started them, they have no slug or user; `check_db_roles` would have crashed on them).
- tests: test_dl341_pool_all_oses.py (new); test_dl310 and test_dl316 updated for the new labels and `CI_RUNS_ON_WINDOWS` value.
- docs: docs/features/runner-pool/spec.md (R5.48 to R5.52, test rows, code map), docs/features/runner-pool/changes/DL341.md, docs/architecture/changes/DL341-pool-all-oses.md.

## Tests (all from claude/plugins/delivery/tests, python3 -m unittest)

- test_dl341_pool_all_oses: 22 tests, OK
- test_dl310_windows_runner: 42, OK
- test_dl315_runner_remove_token: 4, OK
- test_dl316_windows_only_generic: 16, OK
- test_dl318_doctor_locked_runner: 8, OK
- test_dl323_pool_agents_per_repo: 9, OK
- test_dl339_hook_python: 8, OK
- test_doctor: 19, OK; test_ci_setup: 29, OK
- test_runner_pool: 149 tests, 1 failure (test_task_uses_absolute_paths_and_runs_at_boot_not_every_minute). It fails the same way on the base branch without my changes (Linux path separators), so it is not caused by DL341.
- docs_check.py: only W1 (this report under docs/work, expected on the branch; strip before the join).

## Sample pool_status output (fixtures)

```
Machine
  load: memory 41%, cpu 12%, 5s old (limits memory 85%, cpu 60%)
  CI slots: 1 of 2 in use - slot 1 owner/app test-win run 11 (30s)
  light slots: 0 of 1 in use
  heavy slots: none
  queue: empty

Runners (registry joined with GitHub)
  pool  name       repo       os       kind       labels                                      state   job           in registry
  main  main-app   owner/app  linux    container  self-hosted,linux,x64,pool-main,repo-app    online  -             yes
  main  host1-app  owner/app  windows  service    self-hosted,Windows,X64,pool-main,repo-app  busy    test-win #11  yes
  main  stray      owner/app  linux    ?          self-hosted,linux,pool-main                 online  -             NO

Jobs
  running: owner/app test-win #11 on host1-app
  queued runs: owner/app #12 ci
  last finished on pool runners:
    repo       job   runner    result   finished
    owner/app  test  main-app  success  2026-11-14T10:00:00Z
```

## Notes

- A Windows runner not in the registry is found by the doctor and status only when its repository is named by some registry entry.
- Not run: real PowerShell, Docker, mutation passes.

READY
