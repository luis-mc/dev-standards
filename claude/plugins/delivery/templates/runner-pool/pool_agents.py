#!/usr/bin/env python3
"""Add and remove pool agents (DL30). Used by the `pool-add-agent` and `pool-remove-agent` commands.

    gh api -X POST repos/OWNER/REPO/actions/runners/registration-token --jq .token \
      | docker exec -i POOL pool-add-agent SLUG OWNER/REPO --private --pool NAME

The token is read from stdin (one line). It is never printed, never written to a file, and removed from any
error text. The agent runs as its own user `r-SLUG` in `/agents/SLUG` (mode 0700), a copy of the runner in
`/opt/runner`, which stays read-only. `.credentials` is never read.
A repository that is not asserted private (`--private`) is refused (contract section 5). Standard library only.
"""
import argparse
import errno
import json
import os
import re
import secrets
import subprocess
import sys

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{0,30}$')
REPO = re.compile(r'^[^/\s]+/[^/\s]+$')
RUNNER_SRC = '/opt/runner'  # pristine copy, read-only; each agent gets its own copy
HOOK_STARTED = '/opt/delivery/hooks/job-started.sh'
HOOK_DONE = '/opt/delivery/hooks/job-completed.sh'


class PoolError(Exception):
    pass


def redact(text, token):
    return text.replace(token, '***') if token else text


def read_token(stream):
    token = stream.readline().strip()
    if not token:
        raise PoolError('no token on stdin')
    return token


def load(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(data.get('agents'), list) else {'agents': []}
    except (OSError, ValueError):
        return {'agents': []}


def save_in_place(path, data):
    """Write onto the same file. A single-file bind mount cannot be replaced."""
    with open(path, 'a+', encoding='utf-8') as f:
        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())


def save(path, data):
    if os.path.ismount(path):
        return save_in_place(path, data)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    try:
        os.replace(tmp, path)
    except OSError as exc:
        if exc.errno not in (errno.EBUSY, errno.EXDEV):
            raise
        save_in_place(path, data)
        try:
            os.remove(tmp)
        except OSError:
            pass


def labels_for(pool, slug):
    return ['self-hosted', 'linux', 'x64', 'pool-%s' % pool, 'repo-%s' % slug]


def sh(argv, **kw):
    """The one place a command runs. Tests replace it."""
    return subprocess.run(argv, capture_output=True, text=True, **kw)


def add_agent(slug, repo, token, pool, private, agents_file='/agents.json', base='/agents', run=sh, createdb=False):
    if not SLUG.match(slug):
        raise PoolError('bad slug %r (lowercase letters, digits, dash)' % slug)
    if not REPO.match(repo):
        raise PoolError('bad repository %r (OWNER/NAME)' % repo)
    if not private:
        raise PoolError('refused: %s is not asserted private. A self-hosted runner for a public repository is not allowed.' % repo)
    user, folder = 'r-%s' % slug, os.path.join(base, slug)
    data = load(agents_file)
    have = [a for a in data['agents'] if a.get('slug') == slug]
    if have:
        folder_have = os.path.join(base, slug)
        if not os.path.isdir(folder_have):
            return 'already added: %s' % slug  # safe to run again
        # A rerun refreshes the database settings (D104): db.env gets every key, the database gets the connect
        # isolation, and the login keeps its password so running jobs are not cut off. The flag only widens.
        widen = createdb and not have[0].get('createdb')
        create_db(slug, folder_have, have[0].get('user', user), run, createdb or bool(have[0].get('createdb')))
        if widen:
            have[0]['createdb'] = True
            save(agents_file, data)
            return 'already added: %s (database settings refreshed, login now has CREATEDB)' % slug
        return 'already added: %s (database settings refreshed)' % slug
    os.makedirs(folder, mode=0o700, exist_ok=True)
    steps = [['useradd', '--system', '--home-dir', folder, '--shell', '/usr/sbin/nologin', user],
             ['cp', '-a', RUNNER_SRC + '/.', folder],
             ['chown', '-R', '%s:%s' % (user, user), folder], ['chmod', '0700', folder]]
    for argv in steps:
        r = run(argv)
        if r.returncode not in (0, 9):  # 9 = user exists
            raise PoolError('%s failed: %s' % (argv[0], redact(r.stderr.strip(), token)))
    labels = labels_for(pool, slug)
    cfg = ['runuser', '-u', user, '--', './config.sh', '--unattended', '--url', 'https://github.com/' + repo,
           '--token', token, '--name', '%s-%s' % (pool, slug), '--labels', ','.join(labels), '--work', '_work', '--replace']
    if not os.path.exists(os.path.join(folder, '.runner')):  # a rerun after a failed step keeps the registration
        r = run(cfg, cwd=folder)
        if r.returncode != 0:
            raise PoolError('runner registration failed: %s' % redact((r.stderr or r.stdout).strip(), token))
    with open(os.path.join(folder, '.env'), 'w', encoding='utf-8') as f:
        f.write('ACTIONS_RUNNER_HOOK_JOB_STARTED=%s\nACTIONS_RUNNER_HOOK_JOB_COMPLETED=%s\nDELIVERY_MACHINE_DIR=/machine\n'
                % (HOOK_STARTED, HOOK_DONE))
    create_db(slug, folder, user, run, createdb)
    entry = {'slug': slug, 'user': user, 'repo': repo, 'private': True, 'labels': labels}
    if createdb:
        entry['createdb'] = True
    data['agents'].append(entry)
    save(agents_file, data)
    return 'added: %s (%s) as %s' % (slug, repo, user)


def _admin_password():
    try:
        with open('/run/secrets/dbadmin', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def _kept_password(path, login):
    """The password already in db.env, so a rerun does not cut off running jobs (D104). None when there is none."""
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith('PGPASSWORD='):
            return line.split('=', 1)[1] or None
    from urllib.parse import urlsplit
    for line in lines:
        key, _, value = line.partition('=')
        if key == 'DATABASE_URL':
            url = urlsplit(value)
            if url.username == login and url.password:
                return url.password
    return None


def new_db_login(slug):
    """A database name, login and a random password for one repository (D40). The password goes to a 0600 file only."""
    return 'db_%s' % slug.replace('-', '_'), 'u_%s' % slug.replace('-', '_'), secrets.token_urlsafe(24)


def create_db(slug, folder, user, run, createdb=False):
    """One database and one login for this repository on the shared sidecar (D40). The password goes only to a 0600 file."""
    db, login, password = new_db_login(slug)
    password = _kept_password(os.path.join(folder, 'db.env'), login) or password
    host = os.environ.get('DELIVERY_DB_HOST', 'db')
    env = dict(os.environ, PGPASSWORD=_admin_password())
    psql = ['psql', '-h', host, '-U', 'postgres', '-v', 'ON_ERROR_STOP=1', '-f', '-']
    # CREATE DATABASE cannot run in a transaction block, so the role and the database are two separate calls.
    # Each skips what exists; a role that exists gets the new password, so db.env stays right on a rerun.
    # CREATEDB is an owner opt-in (D104). Without it a rerun leaves an existing CREATEDB alone.
    alter_opt, create_opt = ('LOGIN CREATEDB', 'LOGIN CREATEDB') if createdb else ('LOGIN', 'LOGIN')
    role_sql = ("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '%s') THEN "
                "ALTER ROLE %s %s PASSWORD '%s'; ELSE CREATE ROLE %s %s PASSWORD '%s'; END IF; END $$;"
                % (login, login, alter_opt, password, login, create_opt, password))
    db_sql = ("SELECT 'CREATE DATABASE %s OWNER %s' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '%s')\\gexec\n"
              % (db, login, db))
    # Only this login may connect to this database (idempotent).
    db_sql += 'REVOKE CONNECT ON DATABASE %s FROM PUBLIC;\nGRANT CONNECT ON DATABASE %s TO %s;\n' % (db, db, login)
    for what, sql in (('login', role_sql), ('database', db_sql)):
        r = run(psql, env=env, input=sql)
        if r.returncode != 0:
            raise PoolError('database setup (%s) failed: %s' % (what, redact((r.stderr or '').strip(), password)))
    path = os.path.join(folder, 'db.env')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        url = 'postgresql://%s:%s@%s:5432/%s' % (login, password, host, db)
        values = (('DATABASE_URL', url), ('PGHOST', host), ('PGPORT', '5432'), ('PGUSER', login),
                  ('PGPASSWORD', password), ('PGDATABASE', db))
        f.write(''.join('%s=%s\n' % kv for kv in values))
    run(['chown', '%s:%s' % (user, user), path])


def remove_agent(slug, token, agents_file='/agents.json', base='/agents', run=sh, delete_files=False):
    data = load(agents_file)
    mine = [a for a in data['agents'] if a.get('slug') == slug]
    if not mine:
        return 'not in the pool: %s' % slug  # safe to run again
    folder = os.path.join(base, slug)
    r = run(['runuser', '-u', mine[0]['user'], '--', './config.sh', 'remove', '--token', token], cwd=folder)
    if r.returncode != 0:
        raise PoolError('runner removal failed: %s' % redact((r.stderr or r.stdout).strip(), token))
    data['agents'] = [a for a in data['agents'] if a.get('slug') != slug]
    save(agents_file, data)
    if delete_files:
        run(['rm', '-rf', folder])
    return 'removed: %s%s' % (slug, ' and its folder' if delete_files else ' (folder kept; use --delete-files)')


def main(argv=None, stdin=None):
    stdin = stdin or sys.stdin
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ('add', 'remove'):
        print('usage: pool_agents.py add|remove ...', file=sys.stderr)
        return 2
    removing = argv.pop(0) == 'remove'
    ap = argparse.ArgumentParser(prog='pool-remove-agent' if removing else 'pool-add-agent')
    ap.add_argument('slug')
    if not removing:
        ap.add_argument('repo')
        ap.add_argument('--private', action='store_true', help='assert the repository is private')
        ap.add_argument('--db-createdb', action='store_true', help='give the database login CREATEDB (owner decision)')
    else:
        ap.add_argument('--delete-files', action='store_true')
    ap.add_argument('--pool', default=os.environ.get('POOL_NAME', 'main'))
    ap.add_argument('--agents', default='/agents.json')
    ap.add_argument('--base', default='/agents')
    args = ap.parse_args(argv)
    token = ''
    try:
        token = read_token(stdin)
        if removing:
            print(remove_agent(args.slug, token, args.agents, args.base, delete_files=args.delete_files))
        else:
            print(add_agent(args.slug, args.repo, token, args.pool, args.private, args.agents, args.base, createdb=args.db_createdb))
    except PoolError as exc:
        print('pool: %s' % redact(str(exc), token), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
