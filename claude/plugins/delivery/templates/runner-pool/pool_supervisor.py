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


def ensure_user(agent, base, run=None, exists=_user_exists, group_exists=_group_exists, stat=os.stat, log=_log):
    """Make sure the agent's system user exists (a rebuilt container loses /etc/passwd; /agents survives).

    The uid and gid come from the owner of /agents/<slug>. Returns True when the user exists afterwards.
    A missing folder logs one line and returns False.
    """
    user, slug = agent['user'], agent['slug']
    if exists(user):
        return True
    run = run or (lambda argv: subprocess.run(argv, check=False).returncode)
    folder = os.path.join(base, slug)
    try:
        st = stat(folder)
    except OSError:
        log('skip %s: folder %s is missing' % (user, folder))
        return False
    if not group_exists(user):
        run(['groupadd', '--system', '--gid', str(st.st_gid), user])
    rc = run(['useradd', '--system', '--uid', str(st.st_uid), '--gid', str(st.st_gid),
              '--home-dir', folder, '--shell', '/usr/sbin/nologin', user])
    if rc not in (0, None):
        log('could not create user %s (exit %s)' % (user, rc))
    return rc in (0, None)


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
    def __init__(self, agents_file, base='/agents', spawn=None, clock=time.monotonic, ensure=None, environ=None):
        self.agents_file, self.base = agents_file, base
        self.environ = environ if environ is not None else os.environ
        self.n_agents = 1
        self.ensure = ensure or (lambda a: True)  # main() passes ensure_user
        self.warned = set()  # slugs already logged as having no user
        self.spawn = spawn or self._default_spawn
        self.clock = clock
        self.state = {}  # slug -> {proc, started, fails, next}
        self.stopping = False

    def agent_env(self):
        """The environment for a new agent: a copy with CI_MAX_PARALLEL set for the current agent count."""
        env = dict(self.environ)
        env['CI_MAX_PARALLEL'] = str(per_agent_parallel(self.environ, self.n_agents))
        return env

    def _default_spawn(self, agent):
        env = self.agent_env()
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--agents', default='/agents.json')
    ap.add_argument('--base', default='/agents')
    ap.add_argument('--grace-sec', type=float, default=290.0)
    args = ap.parse_args(argv)
    for agent in load_agents(args.agents):
        ensure_user(agent, args.base)
    sup = Supervisor(args.agents, args.base, ensure=lambda a: ensure_user(a, args.base))
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
