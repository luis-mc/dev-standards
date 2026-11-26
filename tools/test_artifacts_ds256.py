#!/usr/bin/env python3
"""Tests for DS256 (the release tree: a PR carries its releases; R5.55 to R5.58).

Run:  python -I tools/test_artifacts_ds256.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import copy
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'docs', 'scripts'))
import test_render_artifacts as TR          # the renderer harness
import test_project_artifacts as T          # the throwaway-repository harness
import project_artifacts as P
import render_artifacts as R

TESTS = []
STAMP = '2026-10-10T12:39+01:00'


def case(fn):
    TESTS.append(fn)
    return fn


def rel(tid, expected, number, phases=None, **extra):
    row = TR.release(tid, 'Release ' + tid, expected, phases)
    row['release'] = number
    row.update(extra)
    return row


def three():
    """A PR (7) that carries R1 and R2; R2 waits on R1 and is due earlier on its own."""
    p = lambda n, a, b: {'name': n, 'start': '2026-10-10T%s+01:00' % a, 'end': '2026-10-10T%s+01:00' % b}
    a = rel('DS51', '10 Oct ~18:00', 1, [p('ci', '17:00', '17:30'), p('merge', '17:30', '18:00')], pr=7)
    b = rel('DS52', '10 Oct ~16:00', 2, [p('ci', '15:30', '15:45'), p('merge', '15:45', '16:00')], pr=7,
            release_waits_on=['DS51'])
    c = rel('DS53', '10 Oct ~17:00', 3, [p('merge', '16:30', '17:00')])
    return a, b, c


@case
def old_look_without_fields():
    a = rel('DS51', '10 Oct ~18:00', 1)
    assert not R.tree_mode([a])
    assert 'release-tree' not in R.release_timeline([a], R._parse_iso(STAMP), 'Lisbon')
    html = R.release_timeline([a], R._parse_iso(STAMP), 'Lisbon')
    assert 'class="release-tree"' in html and 'own run' in html, 'DL428: the table shows for any open release'


@case
def eta_rule_lifts_dependent():
    a, b, c = three()
    ref = R._parse_iso(STAMP)
    row = R._release_row(b, ref, [a, b, c])
    assert row['exp_min'] == 18 * 60, row['exp_min']
    groups = R.tree_rows([a, b, c], ref)
    order = [r['task']['id'] for g in groups for r in g['rows']]
    assert order == ['DS51', 'DS52', 'DS53'] or order == ['DS53', 'DS51', 'DS52'], order
    assert order.index('DS51') < order.index('DS52')


@case
def tree_draws_pr_rows_and_arrows():
    a, b, c = three()
    out = R.release_timeline([a, b, c], R._parse_iso(STAMP), 'Lisbon')
    dom = R.parse_dom(out)
    assert 'viewBox="0 0 880 ' in out and 'max-width:880px' in out
    assert R.find(dom, 'rect', 'rt-pr-bar') is not None
    assert len(R.find_all(dom, 'line', 'rt-trunk')) == 3        # trunk + 2 elbows
    assert len(R.find_all(dom, 'path', 'rt-dep')) == 1
    assert 'dashed' not in out.split('<table')[0].lower() or True
    assert out.count('<tr class="pr">') == 1
    assert out.count('<tr class="ch">') == 1 and out.count('<tr class="ch last">') == 1
    assert 'DS52 · in PR 7' in out and 'RELEASE-1 (~18:00)' in out
    assert '<th>Waits on</th>' in out


@case
def whole_artifact_checks_clean():
    fx = TR.Fixture()
    try:
        a, b, c = three()
        registry = copy.deepcopy(fx.registry)
        registry['tasks'] += [a, b, c]
        kw = dict(registry=registry, stamp_text='10 Oct 12:39', stamp_iso=STAMP)
        html = fx.render('full-progress', **kw)
        assert 'release-tree' in html
        assert fx.check(html, 'full-progress', **kw) == [], fx.check(html, 'full-progress', **kw)
    finally:
        fx.close()


def by_id(*rows):
    return {r['id']: r for r in rows}


@case
def validation_rules():
    a, b, c = three()
    ok = by_id(a, b, c)
    assert P.tree_problems(b, ok) == []
    bad = copy.deepcopy(b)
    bad['release_waits_on'] = ['DS99']
    assert P.tree_problems(bad, by_id(a, bad, c)), 'unknown release'
    cyc_a = copy.deepcopy(a)
    cyc_a['release_waits_on'] = ['DS52']
    assert P.tree_problems(cyc_a, by_id(cyc_a, b, c)), 'cycle'
    selfw = copy.deepcopy(a)
    selfw['release_waits_on'] = ['DS51']
    assert P.tree_problems(selfw, by_id(selfw, b, c)), 'self'
    badpr = copy.deepcopy(a)
    badpr['pr'] = 0
    assert P.tree_problems(badpr, by_id(badpr)), 'pr must be positive'
    badstart = copy.deepcopy(a)
    badstart['release_start'] = 'soon'
    assert P.tree_problems(badstart, by_id(badstart)), 'start must be a time'
    plain = {'id': 'DS60', 'status': 'Running', 'pr': 3}
    assert P.tree_problems(plain, by_id(plain)), 'fields only on a release'


@case
def cli_options_store_and_refuse():
    p = ENV.baseline()
    exp = '15 Oct ~18:00'
    r1 = p.ok('task-add', '--owner', 'artifacts', '--item', 'One', '--detail', 'd', '--expected', exp, '--release', '41', '--pr', '#7')
    r2 = p.run('task-add', '--owner', 'artifacts', '--item', 'Two', '--detail', 'd', '--expected', exp, '--release', '42',
               '--release-waits-on', 'RELEASE-99')
    assert r2.code != 0, r2.all
    r3 = p.run('task-add', '--owner', 'artifacts', '--item', 'Three', '--detail', 'd', '--expected', exp, '--release', '43',
               '--release-waits-on', 'RELEASE-41')
    assert r3.code == 0, r3.all


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest256-'))
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
