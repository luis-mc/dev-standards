# DL231 report

Base check: `pool_agents.py` on origin/main contains `CREATE DATABASE`. OK.

## What changed
- `pool_agents.py`: `--db-role NAME` (repeatable) on `pool-add-agent`; stored as `db_roles` on the repo entry in `agents.json`. `check_db_roles` validates names (`^[a-z][a-z0-9_]{0,62}$`; refuses `postgres`, `public`, `pg_*`, any pool login or database name, and roles declared by another repo, naming both). `role_sql` makes each role as admin behind an `IF NOT EXISTS` check on `pg_roles`, then `GRANT <r> TO <login> WITH ADMIN OPTION`. It runs in `create_db` between the login step and the database step. A rerun merges roles and repeats the SQL safely.
- Grant choice: the pool runs `postgres:16` (compose.yaml). In PG16 the grant defaults to INHERIT and SET true, so the project user can SET ROLE to the role and GRANT on its own objects to it. ADMIN OPTION needs no CREATEROLE. No `INHERIT/SET` clauses are written, so the SQL stays valid on older servers.
- Spec R5.27 in runner-pool, including the exists-safe migration rule. Notes: `docs/features/runner-pool/changes/DL231.md`, `docs/architecture/changes/DL231-pool-db-roles.md`.
- Tests: `tests/test_dl231_pool_db_roles.py` (12 tests: SQL for 0/1/2 roles, bad names, cross-repo and login collisions, idempotent guard, add_agent storage and rerun).

## Tests
- `python -m unittest test_dl231_pool_db_roles`: 12 ok.
- `python -m unittest discover -p "test_*pool*.py"`: 365 ok.
- `python3 tools/test_delivery_ci.py --no-mutants`: 78 passed, 0 failed.
- `docs_check.py`: only W1 (reports on the branch, stripped at the join) and M1 on the delivery spec, cleared by `Docs: none` in the latest commit message.
- spec-lint (areas=delivery), final run 43070718908: every delivery job success; "docs check" fails only on W1 (the report, stripped at the join). Earlier run 43070141124 also failed on M1, now fixed.

## Follow-ups
- A project migration that runs `CREATE ROLE` must check `pg_roles` first. No project migration was changed.
- Removing a repo does not drop its roles (they are server-wide).

Branch head before this line: 687241e4fc58e7608973bb4e39ee8602b5134aba

READY
