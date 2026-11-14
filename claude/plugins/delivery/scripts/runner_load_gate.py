#!/usr/bin/env python3
"""Self-hosted runner gate (DELIVERYSPEC DL-79, DL-90): hold a CI job for the machine queue, a free slot and the load.

    runner_load_gate.py [--max-wait-min N] [--poll-sec N] [--on-timeout fail|run] [--log FILE]

Set it as the runner's ACTIONS_RUNNER_HOOK_JOB_STARTED hook (README: install on Windows service and Linux). With the
machine layer set up (machine.json or the slots folder in the machine folder, machine_slots.py) it does this:

  1. takes a queue ticket (a ready pull request and a default-branch run first, then first come first served);
  2. waits until its ticket is first in line AND a CI slot is free AND memory and CPU are under the limits
     (load.py: host figures, plus the container's own cap in the pool), freeing stale slots on the way;
  3. takes the slot (create-new lock file, atomic), removes the ticket and lets the job run;
  4. while it waits it keeps the ci-wait marker of the shard (git branch ci-wait/<sha>/<shard>; the shard is DELIVERY_SHARD when the hook sees it, else the job key): the
     fallback counts the shard as waiting. If the fallback claimed the shard meanwhile, the hook frees the slot and
     exits 3 (claim lost, the job ends without work).

Without the machine layer it is the DL-79 gate: poll the load every 15 s until it is under the limits. After the maximum
wait (default 30 min) it exits 1 (`--on-timeout fail`: the job fails with a clear log line and can be re-run; `run`
lets the job go without a slot). It never kills, suspends or lowers the priority of anything, and it fails open (exit 0,
logged) when the machine cannot be measured or the machine folder cannot be written.

A light job (its GITHUB_JOB or DELIVERY_SHARD matches `runner_gate.light_jobs`, an exact name or a glob; needs
`light_slots` > 0) takes a light slot (slots/light-N.lock) at once, with no queue ticket, and never a CI slot while a
light slot is free. If every light slot is busy it waits in the normal CI queue for a CI slot. The memory and CPU
limits hold it like any job. The log line names the slot: `slot light-1 taken after N s`.

Settings, first found wins: flag, env (DELIVERY_GATE_MAX_WAIT_MIN, DELIVERY_GATE_POLL_SEC, DELIVERY_GATE_ON_TIMEOUT,
DELIVERY_GATE_LOG), `runner_gate` {max_wait_min, poll_sec, on_timeout} in machine.json (the old
~/.claude/luismc-delivery-machine.json when machine.json has none), defaults. Log: <machine folder>/runner-gate.log
when writable, else ~/.claude/luismc-delivery-runner-gate.log (and stdout, which the runner shows in the job's
"Set up job" step). Standard library only.
"""
import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import load as L  # noqa: E402
import machine_slots as MS  # noqa: E402

DEFAULTS = {'max_wait_min': 30.0, 'poll_sec': 15.0, 'on_timeout': 'fail'}


def settings(args=None):
    new = MS.read_config_file()
    machine = new if isinstance(new, dict) and isinstance(new.get('runner_gate'), dict) else L._read(L.machine_file())
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
    explicit = getattr(args, 'log', None) or os.environ.get('DELIVERY_GATE_LOG')
    if explicit:
        return explicit
    if layer_ready() and os.access(MS.machine_dir(), os.W_OK):
        return os.path.join(MS.machine_dir(), 'runner-gate.log')
    return os.path.join(os.path.expanduser('~'), '.claude', 'luismc-delivery-runner-gate.log')


def layer_ready():
    """True when the machine layer is set up here: machine.json or the slots folder exists."""
    return os.path.exists(MS.config_path()) or os.path.isdir(MS.slots_dir())


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


# --- the queue and the slot (DL-90) ----------------------------------------------------------------

def _marker_root():
    """A git checkout the wait marker can be pushed from: DELIVERY_MARKER_ROOT, else the job's workspace when it has
    one (a persistent runner keeps the .git of the last job). None when there is none."""
    for cand in (os.environ.get('DELIVERY_MARKER_ROOT'), os.environ.get('GITHUB_WORKSPACE')):
        if cand and os.path.exists(os.path.join(cand, '.git')):
            return cand
    return None


def plugin_fallback_path():
    """The plugin's own copy of ci_fallback.py, found relative to this script."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), 'templates', 'shared', 'scripts', 'delivery', 'ci_fallback.py')


def _load_module(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('ci_fallback_of_project', path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001
        return None
    finally:
        sys.path.pop(0)
    return mod


def _fallback(root):
    """The ci_fallback module: the checkout's scripts/delivery/ci_fallback.py when it has one, else the plugin's own copy
    (the job-completed hook empties the workspace, so the next job often has none). None when neither loads."""
    for path in (os.path.join(root, 'scripts', 'delivery', 'ci_fallback.py'), plugin_fallback_path()):
        if os.path.isfile(path):
            mod = _load_module(path)
            if mod is not None:
                return mod
    return None


class Marker:
    """The ci-wait marker of this job's shard. Every call fails open: no checkout, no shard, no git means no marker.
    Whenever there is no marker, one log line says why (`skipped`)."""

    def __init__(self, env=None, log=print):
        env = os.environ if env is None else env
        self.sha, self.shard = env.get('GITHUB_SHA') or '', MS.shard_from_env(env)
        self.holder = 'runner-' + (env.get('RUNNER_NAME') or 'host')
        self.log = log
        self.mod = None
        self.root = None
        self.skipped = ''
        self.remote = env.get('DELIVERY_MARKER_REMOTE') or 'origin'
        if not self.sha:
            self.skipped = 'no commit sha (GITHUB_SHA is empty)'
        elif not self.shard:
            self.skipped = 'no shard (neither DELIVERY_SHARD nor GITHUB_JOB is set)'
        else:
            self.root = _marker_root()
            if not self.root:
                self.skipped = ('no git checkout to push from (no .git in DELIVERY_MARKER_ROOT or GITHUB_WORKSPACE; '
                                'set DELIVERY_MARKER_ROOT in the runner .env)')
            else:
                self.mod = _fallback(self.root)
                if not self.mod:
                    self.skipped = 'ci_fallback.py could not be loaded (not in the checkout and not in the plugin)'
        self.on = False

    def start(self):
        if not self.mod:
            self.log('runner gate: no ci-wait marker written: %s' % self.skipped)
            return
        try:
            self.on = bool(self.mod.mark_wait(self.root, self.remote, self.sha, self.shard, self.holder))
            if not self.on:
                self.log('runner gate: the ci-wait marker for shard %s was not written (git push to %s failed; the '
                         'runner account may have no git credentials: see the guide, Set up CI)'
                         % (self.shard, self.remote))
        except Exception as exc:  # noqa: BLE001
            self.log('runner gate: could not write the ci-wait marker (%s: %s)' % (type(exc).__name__, exc))

    def stop(self):
        if self.mod and self.on:
            try:
                self.mod.clear_wait(self.root, self.remote, self.sha, self.shard)
            except Exception:  # noqa: BLE001
                pass
            self.on = False

    def claim_lost(self):
        if not self.mod:
            return False
        try:
            return bool(self.mod.claim_taken(self.root, self.remote, self.sha, self.shard))
        except Exception:  # noqa: BLE001
            return False


def _ticket_state(ticket, mcfg):
    """Why a ticket is not in the queue list, for the log."""
    path = os.path.join(MS.queue_dir(), ticket['file'])
    if not os.path.exists(path):
        return 'file missing in %s' % MS.queue_dir()
    rec = MS._read_json(path)
    if rec is None:
        return 'file unreadable'
    return 'file present; gate pid %s alive %s; age %.0f s' % (rec.get('gate_pid'), MS.pid_alive(rec.get('gate_pid')),
                                                              time.time() - (rec.get('queued_ts') or 0))


def _got(lock, ident, marker, waited_s, log):
    """A slot was taken: stop the marker, give the slot back when the fallback claimed the shard, else go."""
    marker.stop()
    label = MS.slot_label(lock)
    if marker.claim_lost():
        MS.free_slot(lock, 'claim-lost')
        log('runner gate: claim lost: the fallback claimed shard %s while the job was held; '
            'ending without work, slot %s freed' % (ident['shard'], label))
        return 3, None
    log('runner gate: slot %s taken after %.0f s; starting the job' % (label, waited_s))
    return 0, lock


def _timed_out(cfg, text, waited_s, marker, log):
    marker.stop()
    log('runner gate: TIMED OUT after %.0f s (%s; top processes %s). %s'
        % (waited_s, text, L.top_processes(),
           'Failing the job so it can be re-run when the machine is quiet.' if cfg['on_timeout'] == 'fail'
           else 'on_timeout=run: starting the job without a slot.'))
    return (1 if cfg['on_timeout'] == 'fail' else 0), None


def _ci_wait(lim, cfg, ident, sample=None, sleep=time.sleep, clock=time.monotonic, log=print, marker=None,
               priority=None):
    """Take a ticket and wait for: first in line, a free slot, load under the limits. Then take the slot. Returns
    (code, lock): 0 go (lock is the slot record, or None when `on_timeout` is run or the load cannot be measured),
    1 timed out, 3 the fallback claimed the shard while this job was held (the slot is already freed again)."""
    sample = sample or L.sample
    mcfg = MS.machine_config()
    started = clock()
    deadline = started + cfg['max_wait_min'] * 60.0
    light = MS.is_light_job(ident, mcfg)
    ticket = None
    queued_ts = None
    if light:
        log('runner gate: light job %s (shard %s): trying a light slot first' % (ident['job'], ident['shard']))
    else:
        ticket = MS.enqueue(ident, priority)
        queued_ts = ticket['queued_ts']
        log('runner gate: ticket %s (priority %d) for %s run %s job %s'
            % (ticket['file'], ticket['priority'], ident['repo'], ident['run_id'], ident['job']))
    marker = marker or Marker(log=log)
    waited = False
    last = ''
    try:
        while True:
            for f in MS.free_stale(mcfg):
                log('runner gate: freed slot %s (%s): held by %s run %s job %s'
                    % (MS.slot_label(dict(f['holder'], slot=f['slot'], kind=f.get('kind'))), f['reason'],
                       f['holder'].get('repo'), f['holder'].get('run_id'),
                       f['holder'].get('job')))
            why = []
            if light and MS.free_light_count(mcfg) > 0:
                # A light job never waits for the CI queue while a light slot is free. The limits still hold it.
                try:
                    over = L.over(sample(), lim)
                except Exception as exc:  # noqa: BLE001
                    log('runner gate: cannot measure the machine (%s: %s); taking a slot without a load check'
                        % (type(exc).__name__, exc))
                    over = []
                if not over:
                    lock = MS.take_slot(ident, mcfg, kind='light')
                    if lock is not None:
                        return _got(lock, ident, marker, clock() - started, log)
                    over = ['lost the race for the light slot']
                text = '; '.join(over)
                if not waited:
                    waited = True
                    marker.start()
                    log('runner gate: holding the job (%s); polling every %.0f s for up to %.0f min'
                        % (text, cfg['poll_sec'], cfg['max_wait_min']))
                elif text != last:
                    log('runner gate: still holding (%s)' % text)
                last = text
                if clock() + cfg['poll_sec'] > deadline:
                    return _timed_out(cfg, text, clock() - started, marker, log)
                sleep(cfg['poll_sec'])
                continue
            if ticket is None:                      # light job, every light slot busy: wait in the CI queue
                log('runner gate: every light slot is busy; taking a CI slot in queue order')
                ticket = MS.enqueue(ident, priority)
                queued_ts = ticket['queued_ts']
            if ticket is not None:
                MS.beat(ticket)
            q = MS.queue_list(mcfg)
            if not any(t.get('file') == ticket['file'] for t in q):
                # The own ticket vanished (dropped as unreadable or stale, or removed). Never wait on an empty
                # queue: write it again, with the first queued time so it keeps its place.
                log('runner gate: own ticket was gone; queued again (%s)' % _ticket_state(ticket, mcfg))
                MS.dequeue(ticket)
                try:
                    keep = time.time() - queued_ts < mcfg['slot_stale_min'] * 60
                    ticket = MS.enqueue(ident, ticket['priority'], now=queued_ts if keep else None,
                                       beat_now=time.time())
                    queued_ts = ticket['queued_ts']
                except OSError as exc:
                    log('runner gate: cannot queue again (%s)' % exc)
                else:
                    q = MS.queue_list(mcfg)
            if not q or q[0].get('file') != ticket['file']:
                why.append('%d ahead in the queue' % max(0, next((i for i, t in enumerate(q)
                                                                    if t.get('file') == ticket['file']), len(q))))
            if MS.free_count(mcfg) == 0:
                why.append('no free slot (all %d busy)' % mcfg['ci_slots'])
            if not why:
                try:
                    s = sample()
                    why += L.over(s, lim)
                except Exception as exc:  # noqa: BLE001
                    log('runner gate: cannot measure the machine (%s: %s); taking a slot without a load check'
                        % (type(exc).__name__, exc))
            if not why:
                lock = MS.take_slot(ident, mcfg, queued_ts=queued_ts)
                if lock is not None:
                    return _got(lock, ident, marker, clock() - started, log)
                why.append('lost the race for the slot')
            text = '; '.join(why)
            if not waited:
                waited = True
                marker.start()
                log('runner gate: holding the job (%s); polling every %.0f s for up to %.0f min'
                    % (text, cfg['poll_sec'], cfg['max_wait_min']))
            elif text != last:
                log('runner gate: still holding (%s)' % text)
            last = text
            if clock() + cfg['poll_sec'] > deadline:
                return _timed_out(cfg, text, clock() - started, marker, log)
            sleep(cfg['poll_sec'])
    finally:
        if ticket is not None:
            MS.dequeue(ticket)
        marker.stop()


def _heavy_wait(cfg, ident, mcfg, sample, sleep, clock, log, marker):
    """Take a heavy slot (DL327), polling with no CI slot and no ticket held. Returns (code, lock, waited_s):
    0 with the lock, 0 with None (timed out and on_timeout is run), 1 timed out."""
    started = clock()
    deadline = started + cfg['max_wait_min'] * 60.0
    waited = False
    while True:
        for f in MS.free_stale(mcfg):
            log('runner gate: freed slot %s (%s): held by %s run %s job %s'
                % (MS.slot_label(dict(f['holder'], slot=f['slot'], kind=f.get('kind'))), f['reason'],
                   f['holder'].get('repo'), f['holder'].get('run_id'), f['holder'].get('job')))
        lock = MS.take_slot(ident, mcfg, kind='heavy')
        if lock is not None:
            if waited:
                log('runner gate: heavy slot %s taken after %.0f s' % (MS.slot_label(lock), clock() - started))
            return 0, lock, clock() - started
        h = MS.heavy_holder(mcfg) or {}
        who = '%s run %s job %s' % (h.get('repo'), h.get('run_id'), h.get('job'))
        if not waited:
            waited = True
            marker.start()
            log('runner gate: heavy job %s waits for the heavy slot (held by %s); polling every %.0f s for up to %.0f min'
                % (ident['job'], who, cfg['poll_sec'], cfg['max_wait_min']))
        if clock() + cfg['poll_sec'] > deadline:
            code, _ = _timed_out(cfg, 'no free heavy slot (held by %s)' % who, clock() - started, marker, log)
            return code, None, clock() - started
        sleep(cfg['poll_sec'])


def queue_wait(lim, cfg, ident, sample=None, sleep=time.sleep, clock=time.monotonic, log=print, marker=None,
               priority=None):
    """The gate. A heavy job (runner_gate.heavy_jobs, DL327) takes a heavy slot first, with no CI slot held while it
    waits, then goes through the CI queue. Same return as _ci_wait; the heavy slot is freed again when no CI slot
    was taken (job-done frees both otherwise)."""
    mcfg = MS.machine_config()
    if not MS.is_heavy_job(ident, mcfg):
        return _ci_wait(lim, cfg, ident, sample, sleep, clock, log, marker, priority)
    started = clock()
    marker = marker or Marker(log=log)
    log('runner gate: heavy job %s (shard %s): taking a heavy slot first' % (ident['job'], ident['shard']))
    try:
        code, heavy, _ = _heavy_wait(cfg, ident, mcfg, sample, sleep, clock, log, marker)
    finally:
        marker.stop()
    if heavy is None:
        return code, None
    rest = dict(cfg, max_wait_min=max(0.0, cfg['max_wait_min'] - (clock() - started) / 60.0))
    try:
        code, lock = _ci_wait(lim, rest, ident, sample, sleep, clock, log, marker, priority)
    except BaseException:
        MS.free_slot(heavy, 'error')
        raise
    if lock is None:
        MS.free_slot(heavy, 'no-ci-slot')
    return code, lock


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
    if not layer_ready():
        return wait(L.limits(), settings(args), log=log)
    lim = L.limits()
    try:
        code, _ = queue_wait(lim, settings(args), MS.ident_from_env(), log=log)
    except OSError as exc:
        log('runner gate: the machine folder %s cannot be used (%s); falling back to the load check only'
            % (MS.machine_dir(), exc))
        return wait(L.limits(), settings(args), log=log)
    return code


if __name__ == '__main__':
    sys.exit(main())
