# DL40 report: setup and plan fixes

Branch: DL40-setup-plan-fixes

## Files changed
- claude/plugins/delivery/scripts/delivery_runner_pool.py
- claude/plugins/delivery/tests/test_runner_pool.py (30 new tests, fixtures only)
- docs/features/delivery/shared-self-hosted-runners.md (6.1 to 6.3 only)
- docs/guides/set-up-ci.md (plan, deletions, your part)
- docs/features/delivery/changes/DL40.md, docs/architecture/changes/DL40-setup-plan-fixes.md (change: patch)

## What each point does
- P1: `plan` with no repos uses `derive_repos(found)`: private repos with a runner or a `self-hosted` workflow; Windows = repos with a Windows runner. Nothing derived: no steps, `blocked` set, no removal. Removals, folder and service deletes are limited to the planned repos.
- P2: runner removal is `delete: true`, names the runner.
- P3: new `windows-service-remove` step (elevated, delete, prints `sc.exe stop` and `sc.exe delete`), then the folder delete. `run` checks it with `default_check` (service gone).
- P4: two steps. `host-load-files` copies load.py, machine_slots.py and a loop script (sleeps 15 s) to `<machine dir>/host-load/`. `host-load-task` prints `schtasks /Create /SC ONSTART /RU SYSTEM` with absolute python and loop paths. Choice: one boot task plus a loop (four triggers cannot go under one minute in schtasks). Only on a Windows host.
- P5: `wslconfig` step (state `already` when the file has at least the values) and `wsl-restart` (refuses while a runner is busy). `.wslconfig` is edited in [wsl2] with a `.bak`, no duplicate keys.
- P6: services read PathName, so the folder is found; containers also from `wsl docker ps` on Windows (`via: wsl`, delete goes through wsl). `detect` has `host` figures; `measured_sizing` uses them, and the `.wslconfig` memory as Docker's ceiling. `sizing`/`plan` CLI measure when `--total-gib`/`--cpus` are missing.

## Decisions
- The pool's own labelled container is no longer in the delete list (a re-run would have deleted the new pool).
- A refused sizing gives a blocked plan with no steps.
- The Windows add-service step (DL39's hook lines) is untouched.

## For the orchestrator (not mine to edit)
- `delivery_ci_setup.py` `cmd_pool`: still takes `--total-gib` by hand (`cap=None` without it), still defaults `--repos` to empty (now derived, fine), and its own `check` treats every non-`windows-service` step as the schtasks check. `P.run` now checks `windows-service-remove` itself, so it works, but `cmd_pool` should call `P.measured_sizing(found, ...)` and exit when `pl["blocked"]`. Its `render_plan` may want to show `blocked`.
- `--used-gib` default there is 0.0.

## Ran
- `python3 -I -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests`: 541 tests OK.
- `python3 tools/ci_areas.py --branch-advice`: heavy (delivery). The spec-lint workflow run needs `gh`, which is not in this session; not run.
- No mutation passes, no Docker, no network.
- UI: no UI change.
