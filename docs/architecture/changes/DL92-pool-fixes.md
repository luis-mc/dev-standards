---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The runner pool setup now writes RUNNER_SHA256 into the pool .env, so `docker compose up --no-build` works, and the doctor fails when .env lacks a value for any required compose variable. A changed cap recreates the pool when no job runs (else the exact command is printed), and the doctor compares the live container (docker inspect) with POOL_MEM and POOL_CPUS. The sizing step refuses a cap below 4 GiB and 2 CPUs, no longer counts the pool's own database container as another container, and no longer lets a low WSL ceiling shrink the pool. ci_watch reports exit code 137 or Killed as "killed for memory" with the pool cap, and a slow failure in "Set up runner" as a runner start-up failure, never as a stale lockfile.
