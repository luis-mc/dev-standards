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


def add_agent(slug, repo, token, pool, private, agents_file='/agents.json', base='/agents', run=sh):
    if not SLUG.match(slug):
        raise PoolError('bad slug %r (lowercase letters, digits, dash)' % slug)
    if not REPO.match(repo):
        raise PoolError('bad repository %r (OWNER/NAME)' % repo)
    if not private:
        raise PoolError('refused: %s is not asserted private. A self-hosted runner for a public repository is not allowed.' % repo)
    user, folder = 'r-%s' % slug, os.path.join(base, slug)
    data = load(agents_file)
    if any(a.get('slug') == slug for a in data['agents']):
        return 'already added: %s' % slug  # safe to run again
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
    create_db(slug, folder, user, run)
    data['agents'].append({'slug': slug, 'user': user, 'repo': repo, 'private': True, 'labels': labels})
    save(agents_file, data)
    return 'added: %s (%s) as %s' % (slug, repo, user)


def new_db_login(slug):
    """A database name, login and a random password for one repository (D40). The password goes to a 0600 file only."""
    return 'db_%s' % slug.replace('-', '_'), 'u_%s' % slug.replace('-', '_'), secrets.token_urlsafe(24)


def create_db(slug, folder, user, run):
    """One database and one login for this repository on the shared sidecar (D40). The password goes only to a 0600 file."""
    db, login, password = new_db_login(slug)
    host = os.environ.get('DELIVERY_DB_HOST', 'db')
    try:
        with open('/run/secrets/dbadmin', encoding='utf-8') as f:
            admin = f.read().strip()
    except OSError:
        admin = ''
    env = dict(os.environ, PGPASSWORD=admin)
    psql = ['psql', '-h', host, '-U', 'postgres', '-v', 'ON_ERROR_STOP=1', '-f', '-']
    # CREATE DATABASE cannot run in a transaction block, so the role and the database are two separate calls.
    # Each skips what exists; a role that exists gets the new password, so db.env stays right on a rerun.
    role_sql = ("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '%s') THEN "
                "ALTER ROLE %s LOGIN PASSWORD '%s'; ELSE CREATE ROLE %s LOGIN PASSWORD '%s'; END IF; END $$;"
                % (login, login, password, login, password))
    db_sql = ("SELECT 'CREATE DATABASE %s OWNER %s' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '%s')\\gexec\n"
              % (db, login, db))
    for what, sql in (('login', role_sql), ('database', db_sql)):
        r = run(psql, env=env, input=sql)
        if r.returncode != 0:
            raise PoolError('database setup (%s) failed: %s' % (what, redact((r.stderr or '').strip(), password)))
    path = os.path.join(folder, 'db.env')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write('DATABASE_URL=postgresql://%s:%s@%s/%s\n' % (login, password, host, db))
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
            print(add_agent(args.slug, args.repo, token, args.pool, args.private, args.agents, args.base))
    except PoolError as exc:
        print('pool: %s' % redact(str(exc), token), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
