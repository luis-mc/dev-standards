---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
Four runner pool fixes. The host load task check passes when the host load file is under 60 seconds old, because an unelevated `schtasks /Query` of a SYSTEM task is denied. The pool builds the latest actions/runner release, with a floor of 2.329.0 and a pinned fallback of 2.338.2, and writes `RUNNER_VERSION` to the pool `.env`. The agent database step creates the login and the database in two separate psql calls, skips what exists, and a rerun with a `.runner` file skips `config.sh`. The memory cap no longer shrinks on a rerun: the WSL VM and the pool's containers are left out of used memory, `.wslconfig` is not lowered under other containers, and the step text shows old -> new values.
