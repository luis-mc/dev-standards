#!/usr/bin/env python3
"""Warn-mode report (R5.70, owner decision D3).

A project that runs the delivery rules with enforcement.mode "warn" never gets blocked. The hooks log each finding
they would have blocked to .delivery/blocks.log as `time<TAB>hook:warn<TAB>rule<TAB>message`. This command counts
those lines per rule and prints "would have blocked N times".

  delivery_report.py [--root DIR] [--since ISO] [--json] [--write]

--write also writes .delivery/warn-report.json, which Full Progress reads for its one summary line.
Exit 0 always. Standard library only; it never edits the ledger or the log.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

REPORT_REL = os.path.join('.delivery', 'warn-report.json')
LOG_REL = os.path.join('.delivery', 'blocks.log')
SCHEMA = 1


def find_root(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, '.delivery')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def mode_of(root):
    try:
        with open(os.path.join(root, '.delivery', 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        m = (cfg.get('enforcement') or {}).get('mode')
    except (OSError, ValueError, AttributeError):
        m = None
    return m if m in ('block', 'warn') else 'block'


def count(root, since=None):
    """{'rules': {rule: n}, 'total': n, 'first': time|None, 'last': time|None} over the warn lines of blocks.log."""
    rules, first, last = {}, None, None
    try:
        with open(os.path.join(root, LOG_REL), encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        parts = line.split('\t')
        if len(parts) < 3 or not parts[1].endswith(':warn'):
            continue
        if since and parts[0] < since:
            continue
        rules[parts[2]] = rules.get(parts[2], 0) + 1
        first = first or parts[0]
        last = parts[0]
    return {'rules': rules, 'total': sum(rules.values()), 'first': first, 'last': last}


def build(root, since=None):
    c = count(root, since)
    return {'schema': SCHEMA, 'mode': mode_of(root), 'total': c['total'], 'rules': c['rules'],
            'first': c['first'], 'last': c['last'],
            'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


def lines(rep):
    if rep['mode'] != 'warn':
        return ['Delivery rules run in block mode; there is no warn-mode report.']
    if not rep['total']:
        return ['Warn mode: nothing would have been blocked.']
    out = ['Warn mode: would have blocked %d time%s.' % (rep['total'], '' if rep['total'] == 1 else 's')]
    for rule, n in sorted(rep['rules'].items(), key=lambda kv: (-kv[1], kv[0])):
        out.append('  %s: would have blocked %d time%s' % (rule, n, '' if n == 1 else 's'))
    return out


def summary_line(rep):
    """One line for Full Progress; None when the project is not in warn mode."""
    if not isinstance(rep, dict) or rep.get('mode') != 'warn':
        return None
    n, r = rep.get('total') or 0, len(rep.get('rules') or {})
    if not n:
        return 'Warn mode: nothing would have been blocked.'
    return 'Warn mode: would have blocked %d time%s across %d rule%s.' % (
        n, '' if n == 1 else 's', r, '' if r == 1 else 's')


def main(argv=None):
    ap = argparse.ArgumentParser(description='Count what the delivery rules would have blocked in warn mode.')
    ap.add_argument('--root', default=None, help='project folder (default: the nearest one with .delivery/)')
    ap.add_argument('--since', default=None, help='count only lines at or after this ISO time')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--write', action='store_true', help='also write .delivery/warn-report.json')
    a = ap.parse_args(argv)
    root = find_root(a.root or os.getcwd())
    if not root:
        print('No .delivery/ folder: this project does not use the delivery rules.')
        return 0
    rep = build(root, a.since)
    if a.write:
        try:
            tmp = os.path.join(root, REPORT_REL) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(rep, f)
            os.replace(tmp, os.path.join(root, REPORT_REL))
        except OSError as exc:
            print('warn-report.json not written (%s)' % exc, file=sys.stderr)
    print(json.dumps(rep) if a.json else '\n'.join(lines(rep)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
