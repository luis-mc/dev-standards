#!/usr/bin/env python3
"""Self-hosted runner gate (DELIVERYSPEC DL-79): hold a CI job until the machine is under its load limits.

    runner_load_gate.py [--max-wait-min N] [--poll-sec N] [--on-timeout fail|run] [--log FILE]

Set it as the runner's ACTIONS_RUNNER_HOOK_JOB_STARTED hook (README: install on Windows service and Linux). It polls the
machine every 15 s (load.py limits: project-less, so machine file over defaults) until memory and CPU are under
their limits, then exits 0 and the job starts. After the maximum wait (default 30 min) it exits 1 (`--on-timeout fail`,
the default: the job fails with a clear log line and can be re-run; `run` lets the job go anyway). It never kills,
suspends or lowers the priority of anything, and it fails open (exit 0, logged) when the machine cannot be measured.

Settings, first found wins: flag, env (DELIVERY_GATE_MAX_WAIT_MIN, DELIVERY_GATE_POLL_SEC, DELIVERY_GATE_ON_TIMEOUT,
DELIVERY_GATE_LOG), `runner_gate` {max_wait_min, poll_sec, on_timeout} in the machine file
(~/.claude/luismc-delivery-machine.json), defaults. Log: ~/.claude/luismc-delivery-runner-gate.log (and stdout, which
the runner shows in the job's "Set up job" step). Standard library only.
"""
import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import load as L  # noqa: E402

DEFAULTS = {'max_wait_min': 30.0, 'poll_sec': 15.0, 'on_timeout': 'fail'}


def settings(args=None):
    machine = L._read(L.machine_file())
    sect = machine.get('runner_gate') if isinstance(machine, dict) and isinstance(machine.get('runner_gate'), dict) \
        else {}
    out = dict(DEFAULTS)
    env = {'max_wait_min': os.environ.get('DELIVERY_GATE_MAX_WAIT_MIN'), 'poll_sec': os.environ.get('DELIVERY_GATE_POLL_SEC'),
           'on_timeout': os.environ.get('DELIVERY_GATE_ON_TIMEOUT')}
    flags = {k: getattr(args, k, None) for k in out}
    for key in out:
        for src in (flags.get(key), env.get(key), sect.get(key)):
            if src is None or src == '':
                continue
            try:
                out[key] = src if key == 'on_timeout' else float(src)
                break
            except (TypeError, ValueError):
                continue
    if out['on_timeout'] not in ('fail', 'run'):
        out['on_timeout'] = 'fail'
    out['poll_sec'] = max(0.0, out['poll_sec'])
    return out


def log_file(args=None):
    return (getattr(args, 'log', None) or os.environ.get('DELIVERY_GATE_LOG')
            or os.path.join(os.path.expanduser('~'), '.claude', 'luismc-delivery-runner-gate.log'))


def wait(lim, cfg, sample=None, sleep=time.sleep, clock=time.monotonic, log=print):
    """Poll until under the limits. Returns 0 go (under limits, or unmeasurable), 1 timed out with on_timeout fail,
    0 timed out with on_timeout run. `sample`, `sleep`, `clock` and `log` are the test seams."""
    sample = sample or L.sample
    started = clock()
    deadline = started + cfg['max_wait_min'] * 60.0
    waited = False
    reasons = set()
    while True:
        try:
            s = sample()
        except Exception as exc:  # noqa: BLE001
            log('runner gate: cannot measure the machine (%s: %s); letting the job start' % (type(exc).__name__, exc))
            return 0
        exceeded = L.over(s, lim)
        if not exceeded:
            if waited:
                log('runner gate: machine is under its limits after %.0f s (waited for %s); starting the job'
                    % (clock() - started, ', '.join(sorted(reasons))))
            else:
                log('runner gate: memory %s%%, CPU %s%% are under the limits; starting the job'
                    % (L._n(s['mem']), L._n(s['cpu'])))
            return 0
        if not waited:
            waited = True
            log('runner gate: machine is over its limits (%s); holding the job, polling every %.0f s for up to %.0f min'
                % ('; '.join(exceeded), cfg['poll_sec'], cfg['max_wait_min']))
        reasons.update(e.split(' ')[0] for e in exceeded)
        if clock() + cfg['poll_sec'] > deadline:
            log('runner gate: TIMED OUT after %.0f s: still over the limits (%s; top processes %s). %s'
                % (clock() - started, '; '.join(exceeded), L.top_processes(),
                   'Failing the job so it can be re-run when the machine is quiet.' if cfg['on_timeout'] == 'fail'
                   else 'on_timeout=run: starting the job anyway.'))
            return 1 if cfg['on_timeout'] == 'fail' else 0
        sleep(cfg['poll_sec'])


def main(argv=None):
    ap = argparse.ArgumentParser(prog='runner_load_gate.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('--max-wait-min', dest='max_wait_min', type=float)
    ap.add_argument('--poll-sec', dest='poll_sec', type=float)
    ap.add_argument('--on-timeout', dest='on_timeout', choices=['fail', 'run'])
    ap.add_argument('--log')
    args = ap.parse_args(argv)
    path = log_file(args)

    def log(line):
        line = '%s %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), line)
        print(line, flush=True)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass
    return wait(L.limits(), settings(args), log=log)


if __name__ == '__main__':
    sys.exit(main())
