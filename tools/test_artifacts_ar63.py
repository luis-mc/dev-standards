#!/usr/bin/env python3
"""Regression tests for AR63 (mark-published refusal names the steps, D21), AR64 (Expected without ~
is accepted and stored with it, D22) and AR65 (Expected is optional on To do and On hold, D23).

Run:  python -I tools/test_artifacts_ar63.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'docs', 'scripts'))
import test_project_artifacts as T          # the throwaway-repository harness
import hook_end_of_turn as HOOK
import render_artifacts as RA

TESTS = []
URL = 'https://claude.ai/artifact/ccc'


def case(fn):
    TESTS.append(fn)
    return fn


@case
def ar63_refusal_names_the_steps_in_order():
    p = ENV.baseline()
    p.run('pending', '--json')
    p.ok('mark-published', 'full-progress', '--url', URL)
    p.ok('set-task-status', 'AR1', 'Waiting', '--expected', '14 Oct ~09:00')
    p.run('pending', '--json', '--refresh')
    p.ok('task-add', '--owner', 'artifacts', '--item', 'New', '--detail', 'd', '--expected', '15 Oct')
    r = p.run('mark-published', 'full-progress', '--url', URL)
    assert r.code != 0 and 'older than the latest record change' in r.all, r.all
    a, b, c = r.all.index('pending --json --refresh'), r.all.index('Artifact tool'), r.all.rindex('mark-published')
    assert a < b < c, r.all
    p.run('pending', '--json', '--refresh')
    assert p.run('mark-published', 'full-progress', '--url', URL).code == 0


@case
def ar63_hook_tells_the_order():
    text = HOOK.build_stale_reason('x.py', ['changed since last publish'])
    assert 'every status change first, then run pending, then publish' in text, text


@case
def ar64_expected_without_tilde_is_stored_with_it():
    p = ENV.baseline()
    tid = p.ok('task-add', '--owner', 'artifacts', '--item', 'A', '--detail', 'd', '--expected', '06 Nov 17:47').out.strip()
    assert p.task(tid)['expected'] == '06 Nov ~17:47', p.task(tid)
    tid2 = p.ok('task-add', '--owner', 'artifacts', '--item', 'B', '--detail', 'd', '--expected', '06 Nov 17:47; note here').out.strip()
    assert p.task(tid2)['expected'] == '06 Nov ~17:47; note here', p.task(tid2)
    p.ok('set-task-status', tid, 'Waiting', '--expected', '07 Nov 09:05')
    assert p.task(tid)['expected'] == '07 Nov ~09:05'
    assert p.run('check').code == 0
    r = p.run('task-add', '--owner', 'artifacts', '--item', 'C', '--detail', 'd', '--expected', 'soon')
    assert r.code != 0


@case
def ar65_to_do_and_on_hold_need_no_expected():
    p = ENV.baseline()
    a = p.ok('task-add', '--owner', 'artifacts', '--item', 'No date', '--detail', 'd').out.strip()
    b = p.ok('task-add', '--owner', 'artifacts', '--item', 'Held', '--detail', 'd', '--status', 'On hold').out.strip()
    assert p.task(a)['expected'] == '' and p.task(b)['expected'] == ''
    assert p.run('check').all and p.run('check').code == 0, p.run('check').all
    html = (p.clone / 'docs' / 'artifacts' / 'full-progress.html')
    files = [f for f in (p.clone / 'docs' / 'artifacts').glob('*.html')]
    assert any('Not scheduled' in f.read_text(encoding='utf-8') for f in files)
    assert p.run('task-add', '--owner', 'artifacts', '--item', 'R', '--detail', 'd', '--status', 'Running').code != 0


@case
def ar65_a_phased_to_do_release_still_takes_expected_from_its_phases():
    p = ENV.baseline()
    tid = p.ok('task-add', '--owner', 'artifacts', '--item', 'R', '--detail', 'd', '--release',
               '--phase', 'ci=10:00-11:00', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-12T09:00:00+01:00'}).out.strip()
    assert p.task(tid)['expected'].startswith('12 Oct ~11:00'), p.task(tid)


@case
def ar65_running_and_waiting_need_an_expected():
    p = ENV.baseline()
    a = p.ok('task-add', '--owner', 'artifacts', '--item', 'No date', '--detail', 'd').out.strip()
    for st in ('Running', 'Waiting'):
        r = p.run('set-task-status', a, st)
        assert r.code != 0 and 'needs an Expected' in r.err, r.all
    p.ok('set-task-status', a, 'Waiting', '--expected', '20 Oct ~10:00')
    assert p.task(a)['expected'] == '20 Oct ~10:00'


@case
def ar65_overdue_and_renderers_do_not_crash():
    import artifact_hourly as H
    now = H.local_now({'timezone': 'UTC'}, None) if hasattr(H, 'local_now') else None
    rows = [{'id': 'X1', 'status': 'To do', 'expected': '', 'item': 'i', 'detail': 'd', 'owner': 'project', 'app': '', 'changed': '2026-10-10T10:00:00+00:00'}]
    try:
        H.overdue_tasks(rows, {'timezone': 'UTC', 'project': {}}, now)
    except KeyError:
        raise
    from datetime import datetime
    assert RA._expected_datetime('', datetime(2026, 10, 10)) is None
    assert RA._soonest(rows[0], datetime(2026, 10, 10)) == (1, datetime.max)


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest63-'))
    (T.TMP / 'nullconfig').write_text('', encoding='utf-8')
    ENV = T.Env()
    passed = failed = 0
    try:
        for fn in TESTS:
            try:
                fn()
                passed += 1
            except Exception:
                failed += 1
                print('FAIL %s' % fn.__name__)
                traceback.print_exc()
    finally:
        T._rmtree(T.TMP)
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
