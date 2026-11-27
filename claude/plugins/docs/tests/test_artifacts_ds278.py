#!/usr/bin/env python3
"""Tests for DS278 (a Running or Waiting release has phases; R5.41a, R5.42c).

Run:  python -I claude/plugins/docs/tests/test_artifacts_ds278.py [CASE ...]
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_project_artifacts as P          # reuses its project fixtures

TESTS = []
ONLY = [a for a in sys.argv[1:] if not a.startswith('--')]
LATE = {'CLAUDE_ARTIFACTS_NOW': '2026-12-01T11:00:00+00:00'}      # after the change date of R5.41a


def case(fn):
    TESTS.append(fn)
    return fn


def new_release(p, status='To do'):
    """A release with an Expected and no phases; returns its task ID."""
    r = p.ok('task-add', '--owner', 'project', '--item', 'Plain release', '--detail', 'd', '--expected', '14 Oct ~18:00',
             '--status', status, '--release', rides=False, env=LATE)
    return r.out.strip()


def edit_registry(p, fn):
    rp = p.clone / 'docs' / 'artifacts' / 'registry.json'
    reg = json.loads(rp.read_text(encoding='utf-8'))
    fn(reg)
    rp.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    p.clone_again('edit')


def found(p, env=LATE):
    """The R5.41a findings and warnings of `check --json`; a hand-edited record also differs from its render, so
    only these are read."""
    j = p.run('check', '--json', env=env).json()
    return ([f['message'] for f in j['findings'] if f['req'] == 'R5.41a'],
            [w['message'] for w in j.get('warnings', []) if 'R5.41a' in w['message']])


def full_progress(p):
    return p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file']) or ''


@case
def test_running_release_needs_phases(env):
    p = env.baseline()
    rel = new_release(p)
    before = p.head()
    for status in ('Running', 'Waiting'):
        r = p.run('set-task-status', rel, status, rides=False, env=LATE)
        assert r.code == 1 and '--phase agents=HH:MM-HH:MM' in r.err and 'R5.41a' in r.err, r.all
    assert p.task(rel)['status'] == 'To do' and p.head() == before
    # a task that rides the release is refused for the same reason
    r = p.run('set-task-status', 'SI1', 'Running', '--rides', rel, env=LATE)
    assert r.code == 1 and '--phase agents=HH:MM-HH:MM' in r.err, r.all
    # exempt: To do, Live, Dropped, a task that ships nothing
    p.ok('set-task-status', rel, 'To do', env=LATE)
    p.ok('set-task-status', 'SI1', 'Running', '--no-release', 'a study of the page', '--expected', '14 Oct', rides=False, env=LATE)
    p.ok('set-task-status', rel, 'Dropped', '--into', 'DS1', env=LATE)
    other = new_release(p)
    p.ok('set-task-status', other, 'Live', env=LATE)
    # phases make Running pass, for the release and for its rider
    third = new_release(p)
    p.ok('set-task-status', third, 'Running', '--phase', 'agents=17:30-18:00', rides=False, env=LATE)
    p.ok('set-task-status', 'AR1', 'Waiting', '--rides', third, env=LATE)
    assert p.run('check', env=LATE).code == 0


@case
def test_no_phases_escape_hatch(env):
    p = env.baseline()
    rel = new_release(p)
    p.ok('set-task-status', rel, 'Running', '--no-phases', 'a docs only release', rides=False, env=LATE)
    assert p.task(rel)['no_phases'] == 'a docs only release', p.task(rel)
    assert p.run('check', env=LATE).code == 0
    # a rider may state the reason on the release it rides
    other = new_release(p)
    p.ok('set-task-status', 'SI1', 'Running', '--rides', other, '--no-phases', 'one small change', env=LATE)
    assert p.task(other)['no_phases'] == 'one small change' and 'no_phases' not in p.task('SI1')
    # phases replace the reason
    p.ok('set-task-status', rel, 'Running', '--phase', 'agents=17:30-18:00', rides=False, env=LATE)
    assert 'no_phases' not in p.task(rel) and p.task(rel)['phases'], p.task(rel)


@case
def test_no_phases_refusals(env):
    p = env.baseline()
    rel = new_release(p)
    before = p.head()
    for argv, word in (
            (['set-task-status', rel, 'Running', '--no-phases', ''], 'two words'),
            (['set-task-status', rel, 'Running', '--no-phases', 'later'], 'two words'),
            (['set-task-status', rel, 'To do', '--no-phases', 'not this time'], 'Running or Waiting'),
            (['set-task-status', rel, 'Running', '--no-phases', 'x ' * 41], 'at most 80'),
            (['set-task-status', 'SI1', 'Running', '--no-release', 'a study', '--no-phases', 'no phases here',
              '--expected', '14 Oct'], 'ships nothing')):
        r = p.run(*argv, rides=False, env=LATE)
        assert r.code == 1 and word in r.err, (argv, r.all)
    p.ok('set-task-status', rel, 'Running', '--phase', 'agents=17:30-18:00', rides=False, env=LATE)
    r = p.run('set-task-status', rel, 'Running', '--no-phases', 'it has some', rides=False, env=LATE)
    assert r.code == 1 and 'already has phases' in r.err, r.all
    assert p.task(rel).get('no_phases') is None


@case
def test_check_finds_a_release_without_phases(env):
    p = env.baseline()
    rel = new_release(p)
    p.ok('set-task-status', rel, 'Running', '--phase', 'agents=17:30-18:00', rides=False, env=LATE)
    p.ok('check', env=LATE)

    def strip(reg):
        t = next(x for x in reg['tasks'] if x['id'] == rel)
        t.pop('phases')
        t['changed'] = '2026-12-01T10:00+00:00'
    edit_registry(p, strip)
    bad, warns = found(p)
    assert len(bad) == 1 and rel in bad[0] and not warns, (bad, warns)
    assert p.run('check', env=LATE).code == 1
    edit_registry(p, lambda reg: next(x for x in reg['tasks'] if x['id'] == rel).update({'no_phases': 'later'}))
    bad, _ = found(p)
    assert len(bad) == 1 and 'two words' in bad[0], bad
    edit_registry(p, lambda reg: next(x for x in reg['tasks'] if x['id'] == rel).update({'no_phases': 'a docs only release'}))
    assert found(p) == ([], [])
    edit_registry(p, lambda reg: next(x for x in reg['tasks'] if x['id'] == 'SI1').update({'no_phases': 'not a release row'}))
    bad, _ = found(p)
    assert len(bad) == 1 and 'belongs to a release' in bad[0], bad


@case
def test_older_row_without_phases_warns(env):
    p = env.baseline()
    rel = new_release(p)
    p.ok('set-task-status', rel, 'Running', '--phase', 'agents=17:30-18:00', rides=False, env=LATE)

    def old(reg):
        t = next(x for x in reg['tasks'] if x['id'] == rel)
        t.pop('phases')
        t['changed'] = '2026-11-25T10:00+00:00'
    edit_registry(p, old)
    bad, warns = found(p)
    assert bad == [] and len(warns) == 1 and rel in warns[0], (bad, warns)


def timeline_figure(html):
    return html.split('<figure class="release-timeline', 1)[1].split('</figure>', 1)[0]


@case
def test_no_phases_diamond_is_an_outline(env):
    p = env.baseline()
    rel = new_release(p)
    p.ok('set-task-status', rel, 'Running', '--no-phases', 'a docs only release', rides=False, env={'CLAUDE_ARTIFACTS_NOW': '2026-10-14T11:00:00+00:00'})
    fig = timeline_figure(full_progress(p))
    assert 'rt-expected rt-nophase' in fig and 'rt-bar' not in fig, fig
    assert 'no phases' in fig
    assert 'Outline diamond' in fig or 'outline diamond' in fig
    # a release with phases keeps the filled diamond
    other = new_release(p)
    p.ok('set-task-status', other, 'Running', '--phase', 'agents=17:30-18:00', rides=False, env={'CLAUDE_ARTIFACTS_NOW': '2026-10-14T11:05:00+00:00'})
    fig = timeline_figure(full_progress(p))
    assert 'class="rt-expected"' in fig and 'rt-expected rt-nophase' in fig, fig


@case
def test_no_phases_live_eta_cell(env):
    p = env.baseline()
    rel = new_release(p)
    now = {'CLAUDE_ARTIFACTS_NOW': '2026-10-14T11:00:00+00:00'}
    p.ok('set-task-status', rel, 'Running', '--no-phases', 'a docs only release', '--pr', '41', rides=False, env=now)
    html = full_progress(p)
    cells = [c for c in html.split('<tr') if 'RELEASE-' in c and rel in c and 'release-tree' not in c]
    assert any('~18:00 · no phases' in c for c in cells), cells
    # the same page twice is the same bytes
    p.ok('render', env=now)
    assert full_progress(p) == html


@case
def test_no_phases_reason_in_the_table(env):
    p = env.baseline()
    rel = new_release(p)
    now = {'CLAUDE_ARTIFACTS_NOW': '2026-10-14T11:00:00+00:00'}
    p.ok('set-task-status', rel, 'Running', '--no-phases', 'a docs only release', '--pr', '41', rides=False, env=now)
    html = full_progress(p)
    assert 'no phases: a docs only release' in html, html[html.find('release-tree'):][:1500]
    p.ok('check', env=now)


def main():
    P.TMP = Path(tempfile.mkdtemp(prefix='ds278-'))
    (P.TMP / 'nullconfig').write_text('', encoding='utf-8')
    passed = failed = 0
    try:
        why = P.real_available()
        if why:
            print('SKIP  %s' % why)
            return 0
        env = P.Env()
        for fn in TESTS:
            if ONLY and not any(o in fn.__name__ for o in ONLY):
                continue
            try:
                fn(env)
                passed += 1
            except Exception:
                failed += 1
                print('FAIL %s' % fn.__name__)
                print('      ' + traceback.format_exc().strip().replace('\n', '\n      ')[-1800:])
    finally:
        P._rmtree(P.TMP)
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
