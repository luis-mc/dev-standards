# DL284 report

Base check: origin/main had `def ensure_user` in pool_supervisor.py. OK.

## What changed
- `ensure_user` (pool_supervisor.py): moves a user or group that holds the agent's uid or gid (`usermod -u` / `groupmod -g`) to the highest free id below min(900, lowest agent id); one log line per move. Fixes an existing agent user whose primary group is wrong (`groupadd` if needed, `usermod -g`). Never moves agent users, root, nobody, nogroup, kvm or ids under 100/65534: logs an error, returns False, moves nothing (both ids are checked first). New injectable `users`, `groups`, `agents`; main passes `agents`.
- pool_agents.py: no twin of ensure_user, not touched.
- Tests: new test_dl284_pool_id_clash.py (8 tests); test_pool_supervisor.py passes empty user/group fakes so it needs no real passwd.
- Docs: new R5.30 in the runner-pool spec (the spec had no sentence on recreating agent users, so I added one requirement); feature note changes/DL284.md; change note docs/architecture/changes/DL284-pool-id-clash.md.

## Tests
- python3 -m unittest test_dl284_pool_id_clash test_pool_supervisor: 18 ok
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed
- spec-lint dispatch (run 43351115821, areas=delivery): every delivery job success; only "docs check" failed, on the expected W1 for docs/work/.
- docs_check locally: M1 on delivery spec fixed with a "Docs: none" line in the commit; W1 expected.

## Follow-ups
- The real pool needs a pool-refresh to pick up the new supervisor.
- Free-id pick treats user and group ids as one pool, so it may skip an id.

Branch head: 19fe54a (plus this report commit)

READY
