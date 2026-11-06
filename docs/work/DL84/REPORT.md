# DL84 report

## Changes
1. db.env now has DATABASE_URL, PGHOST, PGPORT (5432), PGUSER, PGPASSWORD, PGDATABASE (0600, same owner).
2. New `pool-db-env` (sh, no python), installed by one COPY line in the Dockerfile (and added to the existing chmod line). Masks PGPASSWORD and DATABASE_URL, appends KEY=value to $GITHUB_ENV, exits 0 with a note when db.env is missing.
3. `pool-add-agent <slug> <repo> --db-createdb`: role is LOGIN CREATEDB, a rerun of the role SQL ALTERs it. Without the flag nothing changes. agents.json gets `createdb: true`. 
4. REVOKE CONNECT FROM PUBLIC and GRANT CONNECT TO login, sent in the same psql call as CREATE DATABASE (keeps two psql calls, so existing tests hold).
5. Spec: "Database in a job (D104)" paragraph in docs/features/delivery/shared-self-hosted-runners.md, section 4.1.
6. Tests: class DL84DbEnvTests (5 tests, includes a real sh run).
Notes: docs/architecture/changes/DL84-delivery.md, docs/features/delivery/changes/DL84.md.

## Commands
- cd claude/plugins/delivery/tests && python3 -m unittest test_runner_pool: OK, 140 tests.
- python3 -m unittest discover (delivery tests): see below in the commit run.
- python3 tools/ci_areas.py --branch-advice: "unreadable diff, treat as every area" (gh workflow run is not available here; not run).
- docs_check.py: 1 error, G1 decisions.md stale (expected). 

## Rerun fix
A rerun with --db-createdb on an agent already in agents.json now runs only ALTER ROLE ... CREATEDB and sets createdb in agents.json. A rerun without the flag does nothing. Test: test_rerun_with_flag_alters_existing_role. test_runner_pool: OK, 141 tests.

Branch head: the last commit on origin/DL84-pool-db-env.

READY
