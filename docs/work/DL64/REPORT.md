# DL64 report

## Fix
`pool_supervisor.py` now has `ensure_user`. At start, and before every spawn, it checks the agent's user with `pwd.getpwnam`. A missing user is created from the uid and gid of `/agents/<slug>`: `groupadd --system --gid` if the group is missing, then `useradd --system --uid --gid --home-dir --shell /usr/sbin/nologin`. A missing folder logs one line and skips the agent. A user that still does not exist is logged once and the agent backs off like other failures. Commands go through an injectable `run` function.

## Tests
New `tests/test_pool_supervisor.py`: create with uid 999, existing user, missing folder, existing group, back-off with one log line.

## Commands
- `cd claude/plugins/delivery/tests && python3 -m unittest test_pool_supervisor test_runner_pool`: OK, 84 tests.
- `python3 tools/ci_areas.py --branch-advice`: "unreadable diff, treat as every area" (heavy spec-lint workflow); not run.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors; 1 warning T2 on the test-cost spec (not ours).

Branch head SHA: the commit that adds this file (see `git log`).

READY
