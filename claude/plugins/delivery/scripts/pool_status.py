#!/usr/bin/env python3
"""One report of the whole runner pool, across OSes (DL341, D298).

    pool_status.py [--pool NAME] [--json] [--jobs N]

The pool coordinates every self-hosted runner on the machine: Linux container agents, Windows runner services, later macOS.
The report joins four things: the machine (host load, limits, CI/light/heavy slots and the queue), the registry
(`pools/<pool>/agents.json`), GitHub (each registry runner, its labels, online or busy, its current job) and the jobs of every
pool repository (running, queued, the last few finished on pool runners).

Read only. It writes nothing and runs `gh api` reads only, once each; there is no watch loop. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import delivery_runner_pool as P  # noqa: E402
import machine_slots as MS  # noqa: E402

try:
    import load as LOAD  # noqa: E402
except Exception:  # noqa: BLE001
    LOAD = None

RUN_LIMIT = 20  # runs read per repository and state


def _runs(probe, repo, state, per_page):
    data, _why = probe.gh_json(['api', 'repos/%s/actions/runs?status=%s&per_page=%d' % (repo, state, per_page)])
    return [r for r in (data or {}).get('workflow_runs', []) if isinstance(r, dict)] if isinstance(data, dict) else None


def _jobs(probe, repo, run_id):
    data, _why = probe.gh_json(['api', 'repos/%s/actions/runs/%s/jobs?per_page=50' % (repo, run_id)])
    return [j for j in (data or {}).get('jobs', []) if isinstance(j, dict)] if isinstance(data, dict) else []


def machine_part(now=None):
    cfg = MS.machine_config()
    now = time.time() if now is None else now
    figures, age = LOAD.read_host_load(now) if LOAD is not None else (None, None)
    st = MS.status(cfg, now)
    return {'limits': cfg.get('load_limits'), 'ci_slots': cfg.get('ci_slots'), 'light_slots': cfg.get('light_slots'),
            'heavy_slots': cfg.get('heavy_slots'), 'local_heavy': cfg.get('local_heavy'),
            'host_load': dict(figures, age_s=round(age)) if figures else None,
            'slots': st['slots'], 'light': st['light_slots'], 'heavy': st['heavy_slots'], 'queue': st['queue']}


def registry_part(probe, only_pool=None, root=None):
    """{pool: entries} for each pool folder with a readable agents.json."""
    pools = P._pools_dir(root)
    out = {}
    for n in sorted(probe.listdir(pools)):
        if only_pool and n != only_pool:
            continue
        entries, _data = P.registry_read_at(probe, os.path.join(pools, n, 'agents.json'))
        if entries is not None and (probe.isfile(os.path.join(pools, n, 'compose.yaml')) or entries):
            out[n] = entries
    return out


def collect(probe=None, pool=None, root=None, now=None, jobs=5):
    probe = probe or P.Probe()
    reg = registry_part(probe, pool, root)
    report = {'machine': machine_part(now), 'pools': [], 'runners': [], 'jobs': {'running': [], 'queued': [], 'finished': []},
              'notes': []}
    for name, entries in reg.items():
        report['pools'].append({'pool': name, 'entries': len(entries)})
        repos = P.pool_repos(entries)
        gh = {}
        for repo in repos:
            runners = P.github_runners(probe, repo)
            if runners is None:
                report['notes'].append('%s: the runners cannot be read (gh not signed in or no rights)' % repo)
            gh[repo] = runners
        known = set()
        for a in entries:
            if not isinstance(a, dict):
                continue
            rname = P.entry_runner_name(a, name)
            known.add((a.get('repo'), rname))
            g = next((r for r in gh.get(a.get('repo')) or [] if r['name'] == rname), None)
            report['runners'].append(_row(name, a, rname, g, gh.get(a.get('repo')) is None))
        for repo, runners in gh.items():  # a GitHub runner with this pool's label that the registry lacks
            for r in runners or []:
                if P._has_label(r['labels'], 'pool-%s' % name) and (repo, r['name']) not in known:
                    report['runners'].append({'pool': name, 'name': r['name'], 'repo': repo, 'os': r['os'] or '?', 'kind': '?',
                                              'registry': False, 'labels': r['labels'], 'state': _state(r), 'job': None})
        _jobs_part(probe, report, repos, gh, name, jobs)
    return report


def _state(r):
    if not r:
        return 'missing'
    return 'busy' if r.get('busy') else (r.get('status') or '?')


def _row(pool, a, rname, g, unread):
    return {'pool': pool, 'name': rname, 'repo': a.get('repo'), 'os': P.entry_os(a), 'kind': P.entry_kind(a), 'registry': True,
            'labels': (g or {}).get('labels') or a.get('labels') or [], 'state': 'unknown' if unread else _state(g), 'job': None}


def _jobs_part(probe, report, repos, gh, pool, limit):
    names = {r['name'] for rs in gh.values() for r in rs or [] if P._has_label(r['labels'], 'pool-%s' % pool)}
    names |= {x['name'] for x in report['runners'] if x['pool'] == pool}
    for repo in repos:
        running = _runs(probe, repo, 'in_progress', RUN_LIMIT)
        queued = _runs(probe, repo, 'queued', RUN_LIMIT)
        for r in running or []:
            for j in _jobs(probe, repo, r.get('id')):
                if j.get('status') == 'in_progress':
                    row = {'repo': repo, 'run_id': r.get('id'), 'workflow': r.get('name'), 'job': j.get('name'),
                           'runner': j.get('runner_name'), 'started': j.get('started_at')}
                    report['jobs']['running'].append(row)
                    for x in report['runners']:
                        if x['repo'] == repo and x['name'] == j.get('runner_name'):
                            x['job'] = '%s #%s' % (j.get('name'), r.get('id'))
        for r in queued or []:
            report['jobs']['queued'].append({'repo': repo, 'run_id': r.get('id'), 'workflow': r.get('name'),
                                             'created': r.get('created_at')})
        done = _runs(probe, repo, 'completed', limit) or []
        for r in done[:limit]:
            for j in _jobs(probe, repo, r.get('id')):
                if j.get('runner_name') in names:
                    report['jobs']['finished'].append({'repo': repo, 'run_id': r.get('id'), 'job': j.get('name'),
                                                       'runner': j.get('runner_name'), 'result': j.get('conclusion'),
                                                       'finished': j.get('completed_at')})
    report['jobs']['finished'] = sorted(report['jobs']['finished'], key=lambda x: x.get('finished') or '', reverse=True)[:limit]


def _table(rows, cols):
    rows = [[str(c if c is not None else '-') for c in r] for r in rows]
    width = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(cols)]
    line = lambda r: '  '.join(c.ljust(width[i]) for i, c in enumerate(r)).rstrip()  # noqa: E731
    return [line(cols)] + [line(r) for r in rows]


def _slot_line(title, slots):
    if not slots:
        return '%s: none' % title
    used = [s for s in slots if not s.get('free')]
    held = ', '.join('slot %s %s %s run %s (%ss%s)' % (s['slot'], s.get('repo') or '?', s.get('job') or '?', s.get('run_id') or '?',
                                                     s.get('age_s'), ', stale' if s.get('stale') else '') for s in used)
    return '%s: %d of %d in use%s' % (title, len(used), len(slots), (' - ' + held) if held else '')


def render_text(rep):
    m = rep['machine']
    out = ['Machine']
    hl = m['host_load']
    lim = m['limits'] or {}
    out.append('  load: %s (limits memory %s%%, cpu %s%%)' % (
        ('memory %.0f%%, cpu %s%%, %ss old' % (hl['mem'], '-' if hl.get('cpu') is None else '%.0f' % hl['cpu'], hl['age_s']))
        if hl else 'no host-load sample', lim.get('memory_pct'), lim.get('cpu_pct')))
    out.append('  ' + _slot_line('CI slots', m['slots']))
    out.append('  ' + _slot_line('light slots', m['light']))
    out.append('  ' + _slot_line('heavy slots', m['heavy']))
    out.append('  queue: %s' % (', '.join('%s %s (%ss)' % (q.get('repo'), q.get('job'), q.get('wait_s')) for q in m['queue']) or 'empty'))
    out += ['', 'Runners (registry joined with GitHub)']
    if rep['runners']:
        out += ['  ' + l for l in _table([[r['pool'], r['name'], r['repo'], r['os'], r['kind'], ','.join(r['labels']), r['state'],
                                           r['job'], 'yes' if r['registry'] else 'NO'] for r in rep['runners']],
                                         ['pool', 'name', 'repo', 'os', 'kind', 'labels', 'state', 'job', 'in registry'])]
    else:
        out.append('  none (no pool folder or an empty registry)')
    j = rep['jobs']
    out += ['', 'Jobs']
    out.append('  running: %s' % (', '.join('%s %s #%s on %s' % (x['repo'], x['job'], x['run_id'], x['runner']) for x in j['running']) or 'none'))
    out.append('  queued runs: %s' % (', '.join('%s #%s %s' % (x['repo'], x['run_id'], x['workflow']) for x in j['queued']) or 'none'))
    out.append('  last finished on pool runners:')
    out += ['    ' + l for l in (_table([[x['repo'], x['job'], x['runner'], x['result'], x['finished']] for x in j['finished']],
                                        ['repo', 'job', 'runner', 'result', 'finished']) if j['finished'] else ['none'])]
    out += ['', 'Notes: ' + '; '.join(rep['notes'])] if rep['notes'] else []
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='pool_status.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('--pool', help='one pool (default: every pool folder on this machine)')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--jobs', type=int, default=5, help='how many finished jobs to list (default 5)')
    args = ap.parse_args(argv)
    rep = collect(pool=args.pool, jobs=max(1, args.jobs))
    print(json.dumps(rep, indent=2) if args.json else render_text(rep))
    return 0


if __name__ == '__main__':
    sys.exit(main())
