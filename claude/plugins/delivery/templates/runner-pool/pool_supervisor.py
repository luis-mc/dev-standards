#!/usr/bin/env python3
"""Pool supervisor (DL30): runs one runner agent per user from agents.json, inside the pool container.

    pool_supervisor.py [--agents FILE] [--base DIR] [--grace-sec N]

agents.json: {"agents": [{"slug": "app1", "user": "r-app1", "repo": "owner/example-app", "private": true}]}
It re-reads the file every tick. A dead agent restarts with back-off (2, 4, 8 ... up to 300 s; a run of 60 s or
more resets it). On SIGTERM it stops starting agents, asks each to stop, and waits up to the grace period so a
running job can finish. Standard library only.
"""
import argparse
import json
import os
import posixpath
import shutil
import signal
import subprocess
import sys
import time

BACKOFF_MIN, BACKOFF_MAX, HEALTHY_SEC = 2.0, 300.0, 60.0


def load_agents(path):
    """The agents in the file; a missing or bad file gives []. An agent needs a slug and a user."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for a in data.get('agents', []) if isinstance(data, dict) else []:
        if isinstance(a, dict) and a.get('slug') and a.get('user'):
            out.append(a)
    return out


def _log(msg):
    print('pool_supervisor: ' + msg, flush=True)


def _user_exists(user):
    import pwd  # Linux only; imported here so the module loads on Windows test hosts
    try:
        pwd.getpwnam(user)
        return True
    except KeyError:
        return False


def _group_exists(name):
    try:
        import grp
        grp.getgrnam(name)
        return True
    except (KeyError, ImportError):
        return False


def _read_users():
    """(name, uid, gid) for every system user. Linux only."""
    import pwd
    return [(p.pw_name, p.pw_uid, p.pw_gid) for p in pwd.getpwall()]


def _read_groups():
    """(name, gid) for every system group. Linux only."""
    import grp
    return [(g.gr_name, g.gr_gid) for g in grp.getgrall()]


ID_FLOOR, ID_CEILING = 100, 900
KEEP_NAMES = ('root', 'nobody', 'nogroup', 'kvm')


def _move_clash(kind, wanted, owner, rows, keep, ceiling, taken, run, log, dry=False):
    """DL284: free id `wanted` if a user or group other than `owner` holds it.

    kind is 'user' or 'group'; rows are (name, id). Returns True when the id is free afterwards.
    A holder in `keep`, or an id under 100 or at 65534, is never moved: one plain error line, False.
    """
    holders = [name for name, num in rows if num == wanted and name != owner]
    for name in holders:
        if name in keep or wanted < ID_FLOOR or wanted >= 65534:
            log('cannot move %s %s off id %d: it is protected; %s not created' % (kind, name, wanted, owner))
            return False
    if dry:
        return True
    for name in holders:
        new = next((i for i in range(ceiling - 1, ID_FLOOR - 1, -1) if i not in taken), None)
        if new is None:
            log('cannot move %s %s off id %d: no free id below %d' % (kind, name, wanted, ceiling))
            return False
        argv = ['usermod', '-u', str(new), name] if kind == 'user' else ['groupmod', '-g', str(new), name]
        rc = run(argv)
        if rc not in (0, None):
            log('could not move %s %s from id %d to %d (exit %s)' % (kind, name, wanted, new, rc))
            return False
        taken.add(new)
        log('moved %s %s from id %d to %d (agent %s needs %d)' % (kind, name, wanted, new, owner, wanted))
    return True


def ensure_user(agent, base, run=None, exists=_user_exists, group_exists=_group_exists, stat=os.stat, log=_log,
                users=_read_users, groups=_read_groups, agents=None):
    """Make sure the agent's system user exists (a rebuilt container loses /etc/passwd; /agents survives).

    The uid and gid come from the owner of /agents/<slug>. Returns True when the user exists afterwards.
    A missing folder logs one line and returns False.
    DL284: a system user or group that holds the agent's uid or gid (a package added at image build) is moved to a
    free id below the agent range first. An existing user whose primary group is not its own group with the
    folder's gid is fixed. Agent users, root, nobody, nogroup, kvm and ids under 100 are never moved.
    """
    user, slug = agent['user'], agent['slug']
    run = run or (lambda argv: subprocess.run(argv, check=False).returncode)
    have_user = exists(user)
    folder = posixpath.join(base, slug)  # a path inside the Linux container, whatever runs the test
    try:
        st = stat(folder)
    except OSError:
        if have_user:
            return True
        log('skip %s: folder %s is missing' % (user, folder))
        return False
    urows, grows = users(), groups()
    me = next((r for r in urows if r[0] == user), None)
    if have_user and me is not None and me[2] == st.st_gid and (user, st.st_gid) in grows:
        return True
    if have_user and me is None:
        return True  # cannot read the user's group: leave it as it was
    # ids of the agents, to find the range to stay under and the users never moved
    agent_users, agent_ids = {user}, {st.st_uid, st.st_gid}
    for other in agents or ():
        agent_users.add(other['user'])
        try:
            o = stat(posixpath.join(base, other['slug']))
            agent_ids.update((o.st_uid, o.st_gid))
        except OSError:
            pass
    ceiling = min([ID_CEILING] + sorted(agent_ids))
    taken = {r[1] for r in urows} | {r[1] for r in grows} | agent_ids
    keep = set(KEEP_NAMES) | agent_users
    urows_ids = [(n, u) for n, u, _ in urows]
    if not have_user:  # check both ids before anything moves
        if not (_move_clash('group', st.st_gid, user, grows, keep, ceiling, taken, run, log, dry=True)
                and _move_clash('user', st.st_uid, user, urows_ids, keep, ceiling, taken, run, log, dry=True)):
            return False
    if not _move_clash('group', st.st_gid, user, grows, keep, ceiling, taken, run, log):
        return False
    group_ok = (user, st.st_gid) in grows or (not grows and group_exists(user))
    if not group_ok:
        if not group_exists(user):
            rc = run(['groupadd', '--system', '--gid', str(st.st_gid), user])
            if rc not in (0, None):
                log('could not create group %s (exit %s)' % (user, rc))
                return False
    if have_user:
        rc = run(['usermod', '-g', user, user])
        if rc not in (0, None):
            log('could not fix the primary group of %s (exit %s)' % (user, rc))
            return False
        log('fixed the primary group of %s to its own group' % user)
        return True
    if not _move_clash('user', st.st_uid, user, urows_ids, keep, ceiling, taken, run, log):
        return False
    rc = run(['useradd', '--system', '--uid', str(st.st_uid), '--gid', str(st.st_gid),
              '--home-dir', folder, '--shell', '/usr/sbin/nologin', user])
    if rc not in (0, None):
        log('could not create user %s (exit %s)' % (user, rc))
    return rc in (0, None)

TMP_KEYS = ('TMPDIR', 'TMP', 'TEMP')


def ensure_agent_tmp(folder, user, run):
    """DL87 (same as pool_agents.ensure_agent_tmp): the agent's own temp folder (mode 0700) and TMPDIR, TMP, TEMP in its .env. Adds only missing lines."""
    tmp = os.path.join(folder, 'tmp')
    os.makedirs(tmp, mode=0o700, exist_ok=True)
    run(['chown', '%s:%s' % (user, user), tmp])
    run(['chmod', '0700', tmp])
    path = os.path.join(folder, '.env')
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError:
        text = ''
    have = {line.split('=', 1)[0] for line in text.splitlines() if '=' in line}
    add = ''.join('%s=%s\n' % (k, tmp) for k in TMP_KEYS if k not in have)
    if add:
        if text and not text.endswith('\n'):
            text += '\n'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text + add)
        run(['chown', '%s:%s' % (user, user), path])


def prepare_tmp(agent, base, run=None, log=_log):
    """DL87: before a runner starts, its temp folder and .env lines are in place. Returns False if the folder is missing."""
    folder = os.path.join(base, agent['slug'])
    if not os.path.isdir(folder):
        return True  # ensure_user already logged a missing folder
    run = run or (lambda argv: subprocess.run(argv, check=False))
    try:
        ensure_agent_tmp(folder, agent['user'], run)
    except OSError as exc:
        log('could not prepare temp folder for %s: %s' % (agent['user'], exc))
    return True


WINE_TIMEOUT_SEC = 180


def wine_prefix(agent, base):
    """DL179: the agent's own Wine prefix, inside its home (/agents/<slug>)."""
    return posixpath.join(base, agent['slug'], '.wine')


def prepare_wine_prefix(agent, base, run=None, which=shutil.which, exists=os.path.exists, log=_log):
    """DL179: boot a Wine prefix once per agent user, so a job can use or copy it instead of booting a fresh one.

    Does nothing when wine is not on PATH or the prefix already holds system.reg. A failure is logged and never raised.
    Returns the prefix path when wine is present, else None.
    """
    if not which('wine'):
        return None
    prefix = wine_prefix(agent, base)
    if exists(posixpath.join(prefix, 'system.reg')):
        return prefix
    run = run or (lambda argv: subprocess.run(argv, check=False, timeout=WINE_TIMEOUT_SEC + 30).returncode)
    inner = 'xvfb-run -a wineboot --init; wineserver -w'
    argv = ['runuser', '-u', agent['user'], '--', 'env', 'WINEPREFIX=' + prefix, 'WINEDEBUG=-all',
            'timeout', str(WINE_TIMEOUT_SEC), 'sh', '-c', inner]
    try:
        rc = run(argv)
    except Exception as exc:  # a Wine problem must never stop the runner
        log('wine prefix for %s failed: %s' % (agent['user'], exc))
        return prefix
    if rc not in (0, None):
        log('wine prefix for %s failed (exit %s); the runner starts anyway' % (agent['user'], rc))
    return prefix


def per_agent_parallel(environ, n_agents):
    """DL83: the pool's CPU count divided by its agents, at least 1. Jobs size their workers from it."""
    raw = environ.get('POOL_CPUS_INT') or environ.get('CI_MAX_PARALLEL') or '1'
    try:
        cpus = int(str(raw).strip())
    except ValueError:
        cpus = 1
    return max(1, cpus // max(1, n_agents))


def popen_spawn(agent, base, env=None):
    """Start one agent as its own user. The runner's own run.sh handles its job and exits when told to stop.

    runuser keeps the environment, so the job inherits CI_MAX_PARALLEL from env.
    """
    folder = os.path.join(base, agent['slug'])
    argv = ['runuser', '-u', agent['user'], '--', os.path.join(folder, 'run.sh')]
    return subprocess.Popen(argv, cwd=folder, env=env)


class Supervisor:
    def __init__(self, agents_file, base='/agents', spawn=None, clock=time.monotonic, ensure=None, environ=None, which=shutil.which):
        self.agents_file, self.base = agents_file, base
        self.which = which
        self.environ = environ if environ is not None else os.environ
        self.n_agents = 1
        self.ensure = ensure or (lambda a: True)  # main() passes ensure_user
        self.warned = set()  # slugs already logged as having no user
        self.spawn = spawn or self._default_spawn
        self.clock = clock
        self.state = {}  # slug -> {proc, started, fails, next}
        self.stopping = False

    def agent_env(self, agent=None):
        """The environment for a new agent: a copy with CI_MAX_PARALLEL set for the current agent count.

        DL179: with wine on PATH it also sets POOL_WINE_PREFIX to the agent's prepared prefix.
        """
        env = dict(self.environ)
        env['CI_MAX_PARALLEL'] = str(per_agent_parallel(self.environ, self.n_agents))
        if agent is not None and self.which('wine'):
            env['POOL_WINE_PREFIX'] = wine_prefix(agent, self.base)
        return env

    def _default_spawn(self, agent):
        env = self.agent_env(agent)
        _log('agent %s starts with CI_MAX_PARALLEL=%s (%d agents)' % (agent['slug'], env['CI_MAX_PARALLEL'], self.n_agents))
        return popen_spawn(agent, self.base, env)

    def tick(self):
        """One pass: forget removed agents, start missing ones, restart dead ones after their back-off."""
        wanted = {a['slug']: a for a in load_agents(self.agents_file)}
        self.n_agents = max(1, len(wanted))
        for slug in [s for s in self.state if s not in wanted]:
            self._stop_one(slug)
            del self.state[slug]
        if self.stopping:
            return
        now = self.clock()
        for slug, agent in wanted.items():
            st = self.state.setdefault(slug, {'proc': None, 'started': 0.0, 'fails': 0, 'next': 0.0})
            proc = st['proc']
            if proc is not None and proc.poll() is None:
                continue
            if proc is not None:
                ran = now - st['started']
                st['fails'] = 0 if ran >= HEALTHY_SEC else st['fails'] + 1
                st['next'] = now + min(BACKOFF_MAX, BACKOFF_MIN * (2 ** max(0, st['fails'] - 1)))
                st['proc'] = None
            if now >= st['next']:
                if not self.ensure(agent):
                    if slug not in self.warned:
                        self.warned.add(slug)
                        _log('user %s does not exist; will retry with back-off' % agent['user'])
                    st['fails'] += 1
                    st['next'] = now + min(BACKOFF_MAX, BACKOFF_MIN * (2 ** max(0, st['fails'] - 1)))
                    continue
                self.warned.discard(slug)
                st['proc'] = self.spawn(agent)
                st['started'] = now

    def _stop_one(self, slug):
        proc = self.state[slug]['proc']
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def stop(self, grace_sec=300.0, sleep=time.sleep):
        """Graceful stop: ask every agent to end, wait for running jobs, then kill what is left."""
        self.stopping = True
        for slug in self.state:
            self._stop_one(slug)
        end = self.clock() + grace_sec
        while self.clock() < end and any(s['proc'] is not None and s['proc'].poll() is None for s in self.state.values()):
            sleep(1)
        for s in self.state.values():
            if s['proc'] is not None and s['proc'].poll() is None:
                s['proc'].kill()


def kvm_gid(stat=os.stat):
    """DL274: the group id of /dev/kvm inside this container, or None when there is no device."""
    try:
        return stat('/dev/kvm').st_gid
    except OSError:
        return None


VM_CACHE_ROOT = '/ci-tools/vm-cache'


def prepare_kvm(agent, environ=None, run=None, gid_of=kvm_gid, group_name=None, log=_log, isdir=os.path.isdir, vm_cache=False):
    """DL274: with POOL_KVM=1, put the agent user in the group that owns /dev/kvm. The gid is read here, never assumed.
    A group with that gid is reused; else group `kvm` is made with it. Always returns True so the runner starts."""
    env = os.environ if environ is None else environ
    if env.get('POOL_KVM') != '1':
        return True
    gid = gid_of()
    if gid is None:
        log('POOL_KVM=1 but /dev/kvm is missing in the container')
        return True
    run = run or (lambda argv: subprocess.run(argv, check=False).returncode)
    if group_name is None:
        import grp
        def group_name(g):
            try:
                return grp.getgrgid(g).gr_name
            except KeyError:
                return None
    name = group_name(gid)
    if name is None:
        name = 'kvm'
        run(['groupadd', '--gid', str(gid), name])
    if gid != 0:
        run(['usermod', '-aG', name, agent['user']])
    if vm_cache:
        prepare_vm_cache(name, run, isdir=isdir, log=log)
    return True


def prepare_vm_cache(group, run, root=VM_CACHE_ROOT, isdir=os.path.isdir, log=_log):
    """DL281: make the shared VM cache folder root:<kvm group> mode 2775, so every runner user can use it.
    Only when the shared tool volume is mounted; the folder is made again at each start and is safe to repeat."""
    parent = posixpath.dirname(root)
    if not isdir(parent):
        return False
    run(['install', '-d', '-o', 'root', '-g', group, '-m', '2775', root])
    run(['chgrp', group, root])
    run(['chmod', '2775', root])
    return True


def prepare_wine_ok(agent, base):
    """DL179: run prepare_wine_prefix for a real folder only; always True so the runner starts."""
    if os.path.isdir(posixpath.join(base, agent['slug'])):
        prepare_wine_prefix(agent, base)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--agents', default='/agents.json')
    ap.add_argument('--base', default='/agents')
    ap.add_argument('--grace-sec', type=float, default=290.0)
    args = ap.parse_args(argv)
    for agent in load_agents(args.agents):
        ensure_user(agent, args.base, agents=load_agents(args.agents))
    sup = Supervisor(args.agents, args.base, ensure=lambda a: ensure_user(a, args.base, agents=load_agents(args.agents)) and prepare_tmp(a, args.base) and prepare_wine_ok(a, args.base) and prepare_kvm(a, vm_cache=True))
    done = []
    signal.signal(signal.SIGTERM, lambda *_: done.append(1))
    signal.signal(signal.SIGINT, lambda *_: done.append(1))
    while not done:
        sup.tick()
        time.sleep(2)
    sup.stop(args.grace_sec)
    return 0


if __name__ == '__main__':
    sys.exit(main())
