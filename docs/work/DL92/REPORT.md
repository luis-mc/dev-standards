# DL92 report: pool fixes (DL92 DL93 DL94 DL95)

## Changes
- DL92 (B1): `write_pool_files` writes RUNNER_SHA256 to `.env` (the sha the setup resolved; the pinned one for the pinned version). `pool-up` prefers the `.env` value. Doctor check `pool.<n>.required-vars` parses compose.yaml for every `${VAR:?...}` and fails, naming the variable, when `.env` has no value.
- DL93 (B2): the `pool-files` step compares the old and new POOL_MEM/POOL_CPUS. If changed, it runs `docker compose up -d --no-build --force-recreate pool` when no runner is busy; when a runner is busy, or runners cannot be read (treated as busy), it prints the command as a by-hand step. Doctor check `pool.<n>.live-cap` compares `docker inspect` HostConfig.Memory and NanoCpus with `.env` and fails with the recreate command.
- DL94 (B3): `sizing` refuses a cap below 4 GiB / 2 CPUs and says why and what the machine needs. The shard message keeps priority.
- DL95 (B4): `ci_watch.py` failure report adds `diagnose()`: exit code 137 or "Killed" in the failed log tail gives "killed for memory: the runner's cap is N" (N from `docker inspect` of the labelled pool container, else "unknown"); "Set up runner"/"Set up job" failing after 25+ min gives a runner start-up failure pointing at the pool cap. Neither prints a lockfile hint. ci_watch itself never had that hint; the "stale lockfile" text lives in branch_gate.py and hook_pre_tool.py, which this task does not own (see Not done).

## B3 root cause
No single proof is possible from here (the bad run is gone). Two real defects in the sizing step explain 0.5 GiB / 1 CPU (ceiling 2.5 GiB minus the 2 GiB sidecar and VM):
1. The Docker ceiling comes from the current `.wslconfig` memory and the usage of "other" containers is subtracted from it. `container_gib` called every container without the pool label "other", and the pool's own `db` container (postgres, no label) was one. Each rerun therefore saw a ceiling 0.1+ GiB lower, and the setup writes `.wslconfig` memory = cap + 2, so the cap ratcheted down on every rerun. Fixed: a container whose compose project starts with `pool-` is the pool's.
2. A low ceiling (old `.wslconfig`) shrank the pool even when the machine had room, although the setup raises the ceiling itself. Fixed: when the room allows the floor, size up to 4 GiB and let the wslconfig step raise the ceiling.
The floor is the safety net for anything else (a busy machine at measure time).

## Tests
- `python -m unittest test_dl92_pool_fixes` (in claude/plugins/delivery/tests): 23 tests OK.
- `python -m unittest test_dl92_pool_fixes test_runner_pool test_doctor test_watch test_ci_runs test_watch_ci_runs`: 295 run; the same failures as on origin/main (Windows-only: file modes, FakeProbe paths starting C:), no new one. Compared against a temporary worktree of origin/main.
- Real Docker check (load 58% memory, 25% CPU): a throwaway `dl92-test-<n>` alpine container with --memory 64m --cpus 0.5; `docker inspect --format '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}'` gave `67108864 500000000`, the format the code parses. The container was removed. No existing container was touched.

## Docs
Change note docs/architecture/changes/DL92-pool-fixes.md; feature note docs/features/delivery/changes/DL92.md. No spec note: DELIVERYSPEC does not describe the pool .env, doctor or the ci_watch report text.

## Not done (not mine)
- branch_gate.py line ~165 says "A stale lockfile is the usual cause" for any setup failure, and the DL-23 hook text says the same. They should also mention exit 137 / memory.

CI and head SHA: see the bottom section, filled after the run.

NOT READY
