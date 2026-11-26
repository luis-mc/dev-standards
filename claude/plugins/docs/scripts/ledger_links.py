"""R5.59: what the delivery ledger says about open releases. Read-only; nothing here writes a file.

A ledger train has a branch `<TASK-ID>-integration`; that task is the release. The train's `pr` is the
release's carrier PR. A release waits on an earlier open release when its train holds commits of the
other train that are not yet on the base branch, or when `deploy.serial` is true in `.delivery/config.json`
and the other train merged first. Every failure (no ledger, no git, a bad ref) gives nothing.
"""
from __future__ import annotations

import json
import os
import subprocess

MERGED = ('merged', 'live', 'cleaned')


def _num(task):
    n = task.get('release')
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else None


def delivery_root(record_dir: str):
    """The folder above the record folder that holds `.delivery/`, or None."""
    here = os.path.abspath(str(record_dir or '.'))
    for _ in range(5):
        if os.path.isdir(os.path.join(here, '.delivery')):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def _json_file(path: str):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _git(root: str, *args):
    try:
        r = subprocess.run(['git', '-C', root] + list(args), capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.split() if r.returncode == 0 else None


def _train_commits(root: str, branch, base: str):
    if not isinstance(branch, str):
        return None
    for ref in (branch, 'origin/' + branch):
        got = _git(root, 'rev-list', '%s..%s' % (base, ref))
        if got is not None:
            return set(got)
    return None


def _base_ref(root: str, cfg) -> str:
    named = cfg.get('base') if isinstance(cfg.get('base'), str) else ''
    for ref in ([named, 'origin/' + named] if named else []) + ['origin/main', 'main']:
        if _git(root, 'rev-parse', '--verify', '-q', ref):
            return ref
    return 'main'


def _merged_at(train) -> str:
    for ph in (train.get('phases') or {}).get('actual') or []:
        if isinstance(ph, dict) and ph.get('name') == 'merge' and ph.get('end'):
            return str(ph['end'])
    return ''


def links(releases: list, record_dir: str) -> dict:
    """{release task id: {'pr': N or None, 'waits': [release task ids]}} for the open `releases` (task rows)."""
    root = delivery_root(record_dir)
    ledger = _json_file(os.path.join(root, '.delivery', 'ledger.json')) if root else None
    trains = ledger.get('trains') if isinstance(ledger, dict) else None
    if not isinstance(trains, list):
        return {}
    cfg = _json_file(os.path.join(root, '.delivery', 'config.json'))
    cfg = cfg if isinstance(cfg, dict) else {}
    serial = isinstance(cfg.get('deploy'), dict) and cfg['deploy'].get('serial') is True
    by_task = {}
    for tr in trains:
        branch = tr.get('branch') if isinstance(tr, dict) else None
        if isinstance(branch, str) and branch.endswith('-integration'):
            by_task[branch[:-len('-integration')]] = tr
    mine = {t['id']: t for t in releases if t.get('id') in by_task}
    out = {tid: {'pr': None, 'waits': []} for tid in mine}
    for tid in mine:
        pr = by_task[tid].get('pr')
        if isinstance(pr, int) and not isinstance(pr, bool) and pr > 0:
            out[tid]['pr'] = pr
    base, commits = None, {}
    for bid, b in mine.items():
        if b.get('release_waits_on') or _num(b) is None:
            continue
        for aid, a in mine.items():
            if aid == bid or _num(a) is None or _num(a) >= _num(b):
                continue
            ta, tb = by_task[aid], by_task[bid]
            wait = serial and ta.get('state') in MERGED and (tb.get('state') not in MERGED or _merged_at(ta) <= _merged_at(tb))
            if not wait:
                base = base or _base_ref(root, cfg)
                for tid, tr in ((aid, ta), (bid, tb)):
                    if tid not in commits:
                        commits[tid] = _train_commits(root, tr.get('branch'), base)
                wait = bool(commits[aid] and commits[bid] and commits[aid] & commits[bid])
            if wait:
                out[bid]['waits'].append(aid)
    return out


def read(record_dir: str) -> dict:
    """R5.63: {'trains': {release task id: train}, 'agents': [agent rows]} from `.delivery/ledger.json`, read-only.
    A train belongs to the release whose task ID is its branch `<TASK-ID>-integration`. No ledger gives empty parts."""
    root = delivery_root(record_dir) if record_dir else None
    ledger = _json_file(os.path.join(root, '.delivery', 'ledger.json')) if root else None
    out = {'trains': {}, 'agents': []}
    if not isinstance(ledger, dict):
        return out
    for tr in ledger.get('trains') if isinstance(ledger.get('trains'), list) else []:
        branch = tr.get('branch') if isinstance(tr, dict) else None
        if isinstance(branch, str) and branch.endswith('-integration'):
            out['trains'][branch[:-len('-integration')]] = tr
    if isinstance(ledger.get('agents'), list):
        out['agents'] = [a for a in ledger['agents'] if isinstance(a, dict)]
    return out
