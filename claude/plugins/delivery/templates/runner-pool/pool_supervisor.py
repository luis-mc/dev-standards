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


def popen_spawn(agent, base):
    """Start one agent as its own user. The runner's own run.sh handles its job and exits when told to stop."""
    folder = os.path.join(base, agent['slug'])
    argv = ['runuser', '-u', agent['user'], '--', os.path.join(folder, 'run.sh')]
    return subprocess.Popen(argv, cwd=folder)


class Supervisor:
    def __init__(self, agents_file, base='/agents', spawn=None, clock=time.monotonic):
        self.agents_file, self.base = agents_file, base
        self.spawn = spawn or (lambda a: popen_spawn(a, base))
        self.clock = clock
        self.state = {}  # slug -> {proc, started, fails, next}
        self.stopping = False

    def tick(self):
        """One pass: forget removed agents, start missing ones, restart dead ones after their back-off."""
        wanted = {a['slug']: a for a in load_agents(self.agents_file)}
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
    sup = Supervisor(args.agents, args.base)
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
