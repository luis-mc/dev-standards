#!/usr/bin/env python3
"""One Postgres database per test worker, made from a template (CIR10 L8). Postgres projects only.

Why: workers that share one database wait on each other or clean up after each other. Migrating one
template database once and copying it for each worker is fast (the first product's integration part went
from 1,054 s to 698 s, -34%) and keeps the workers apart.

    db_per_worker.py setup   --base NAME --workers N [--run]
    db_per_worker.py teardown --base NAME --workers N [--run]
    db_per_worker.py name    --base NAME [--worker ID]

`setup` prints the SQL: drop and create the template `<base>_tpl`, and (after you migrate it) the
`CREATE DATABASE <base>_w<K> TEMPLATE <base>_tpl` statements. Migrate the template between the two parts:

    db_per_worker.py setup --base app_test --workers 4 --phase template --run   # create the empty template
    <run the project's migrations against app_test_tpl>
    db_per_worker.py setup --base app_test --workers 4 --phase workers --run    # copy it for each worker

`--run` sends the SQL to `psql` using the usual PG* variables (PGHOST, PGUSER, PGPASSWORD, PGPORT) and the
`postgres` database. Without `--run` the SQL is only printed. `name` prints the database of this worker; the
worker id is `--worker`, else JEST_WORKER_ID, VITEST_POOL_ID, TEST_WORKER_INDEX or 1. Point the project's
test setup at that name. Nothing here names a table or a migration tool: those belong to the project.

Names are checked: letters, digits and underscore only, so a name cannot carry SQL.
Exit: 0 ok; 1 psql failed; 2 usage error. Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
WORKER_ENV = ("JEST_WORKER_ID", "VITEST_POOL_ID", "TEST_WORKER_INDEX")


def check_name(base: str) -> str:
    if not NAME_RE.match(base or ""):
        raise ValueError("bad database name %r: letters, digits and underscore, at most 41 characters" % base)
    return base


def template_name(base: str) -> str:
    return check_name(base) + "_tpl"


def worker_db(base: str, worker) -> str:
    n = int(worker)
    if n < 1:
        raise ValueError("worker ids start at 1")
    return "%s_w%d" % (check_name(base), n)


def this_worker(env=None) -> int:
    env = os.environ if env is None else env
    for k in WORKER_ENV:
        v = env.get(k, "")
        if v.isdigit() and int(v) >= 1:
            return int(v)
    return 1


def template_sql(base: str) -> list:
    t = template_name(base)
    return ['DROP DATABASE IF EXISTS "%s" WITH (FORCE);' % t, 'CREATE DATABASE "%s";' % t]


def workers_sql(base: str, workers: int) -> list:
    if workers < 1:
        raise ValueError("--workers must be at least 1")
    t, out = template_name(base), []
    for k in range(1, workers + 1):
        w = worker_db(base, k)
        out.append('DROP DATABASE IF EXISTS "%s" WITH (FORCE);' % w)
        out.append('CREATE DATABASE "%s" TEMPLATE "%s";' % (w, t))
    return out


def teardown_sql(base: str, workers: int) -> list:
    out = ['DROP DATABASE IF EXISTS "%s" WITH (FORCE);' % worker_db(base, k) for k in range(1, workers + 1)]
    return out + ['DROP DATABASE IF EXISTS "%s" WITH (FORCE);' % template_name(base)]


def run_sql(statements, runner=subprocess.run) -> int:
    for s in statements:
        r = runner(["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-d", "postgres", "-c", s])
        if r.returncode != 0:
            print("db_per_worker: psql failed on: %s" % s, file=sys.stderr)
            return 1
    return 0


def main(argv=None, runner=subprocess.run) -> int:
    ap = argparse.ArgumentParser(prog="db_per_worker.py")
    ap.add_argument("cmd", choices=["setup", "teardown", "name"])
    ap.add_argument("--base", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--worker", type=int)
    ap.add_argument("--phase", choices=["template", "workers", "all"], default="all")
    ap.add_argument("--run", action="store_true")
    try:
        a = ap.parse_args(argv)
        if a.cmd == "name":
            print(worker_db(a.base, a.worker if a.worker else this_worker()))
            return 0
        if a.cmd == "teardown":
            sql = teardown_sql(a.base, a.workers)
        else:
            sql = (template_sql(a.base) if a.phase in ("template", "all") else []) + \
                  (workers_sql(a.base, a.workers) if a.phase in ("workers", "all") else [])
    except ValueError as exc:
        print("db_per_worker: %s" % exc, file=sys.stderr)
        return 2
    if not a.run:
        print("\n".join(sql))
        return 0
    return run_sql(sql, runner)


if __name__ == "__main__":
    sys.exit(main())
