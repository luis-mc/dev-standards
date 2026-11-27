#!/usr/bin/env python3
"""Tests for DL429 (Full Progress section 0: status badges and "What is happening"; R5.61 to R5.63).

Run:  python -I claude/plugins/docs/tests/test_artifacts_dl429.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import copy
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
import test_render_artifacts as TR          # the renderer harness
import render_artifacts as R

TESTS = []


def case(fn):
    TESTS.append(fn)
    return fn


def rel(tid, number, status='Running', pr=None, expected='10 Oct ~18:00', **extra):
    row = TR.release(tid, 'Release ' + tid, expected, status=status)
    row['release'] = number
    if pr:
        row['pr'] = pr
    row.update(extra)
    return row


def with_rows(fx, *rows):
    registry = copy.deepcopy(fx.registry)
    registry['tasks'] += list(rows)
    return registry


def write_delivery(fx, trains=(), agents=()):
    folder = os.path.join(fx.root, '.delivery')
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'ledger.json'), 'w', encoding='utf-8') as fh:
        json.dump({'schema': 1, 'trains': list(trains), 'agents': list(agents)}, fh)


def train(tid, pr, state='joined', **extra):
    row = {'id': 'T-2026-10-10-01', 'branch': tid + '-integration', 'pr': pr, 'state': state, 'hold': None,
           'ci': {'run_ids': [], 'state': 'queued'}, 'smoke': {'state': None}, 'phases': {'actual': []},
           'live_at': None}
    row.update(extra)
    return row


def run(run_id, pr, conclusion, job='unit tests', at='2026-10-10T10:00:00Z'):
    steps = [{'job': job, 'name': 'step', 'conclusion': conclusion, 'start_s': 0, 'duration_s': 5}]
    return {'run_id': run_id, 'workflow': 'spec-lint', 'conclusion': conclusion, 'why': 'ready PR #%d' % pr,
            'completed_at': at, 'total_s': 10, 'steps': steps}


def render(fx, registry=None, ci_runs=None, key='full-progress'):
    return R.render_artifact(fx.manifest, registry or fx.registry, fx.contents, key, TR.PLUGIN, fx.record,
                             TR.STAMP_TEXT, TR.STAMP_ISO, ci_runs=ci_runs)


def badges(html):
    root = R.parse_dom(html)
    return {b.attrs['data-badge']: b for b in R.find_all(root, 'span', 'status-badge')}


def bullets(html):
    box = R.find(R.parse_dom(html), 'div', 'what-happens')
    return [R.text_of(li) for li in R.find_all(box, 'li')]


def fixture():
    return TR.Fixture()


@case
def badges_replace_the_collapsible_lines():
    fx = fixture()
    try:
        out = render(fx)
        root = R.parse_dom(out)
        assert R.find(root, 'div', 'status-badges') is not None
        assert R.find(root, 'div', 'at-a-glance') is None and not R.find_all(root, 'details', 'glance-group')
        assert R.find(root, 'div', 'status-count-tiles') is None, 'the count badges replace the tiles'
        assert R.find(root, 'p', 'lede') is None, 'the generated text replaces the lede'
        assert 'All ongoing work in dev-standards' not in out
        got = {k: R.text_of(R.find(b, 'span', 'badge-value')) for k, b in badges(out).items()}
        assert got['needs-you'] == '2' and got['running'] == '3' and got['to-do'] == '2', got
        assert 'badge-alert' in badges(out)['needs-you'].attrs['class']
        assert fx.check(out, 'full-progress') == [], fx.check(out, 'full-progress')
    finally:
        fx.close()


@case
def badge_row_is_full_width():
    fx = fixture()
    try:
        out = render(fx)
        rule = re.search(r'\.status-badges\s*\{([^}]*)\}', out).group(1)
        assert 'width: 100%' in rule and 'max-width' not in rule and 'flex-wrap: wrap' in rule, rule
        box = re.search(r'\.what-happens\s*\{([^}]*)\}', out).group(1)
        assert 'width: 100%' in box and 'max-width' not in box, box
        root = R.parse_dom(out)
        assert not R.has_ancestor(R.find(root, 'div', 'status-badges'), lambda n: has_class(n, 'at-a-glance'))
    finally:
        fx.close()


def has_class(node, name):
    return R.has_class(node, name)


@case
def feature_artifact_keeps_its_glance_and_lede():
    fx = fixture()
    try:
        out = render(fx, key='artifacts')
        root = R.parse_dom(out)
        assert R.find(root, 'div', 'at-a-glance') is not None and R.find(root, 'p', 'lede') is not None
        assert R.find(root, 'div', 'status-badges') is None and R.find(root, 'div', 'what-happens') is None
        assert fx.check(out, 'artifacts') == []
    finally:
        fx.close()


@case
def ci_badge_does_not_flag_a_failure_a_later_run_fixed():
    fx = fixture()
    try:
        registry = with_rows(fx, rel('DS51', 1, pr=7))
        ci = {'active': [], 'finished': [run(1, 7, 'failure'), run(2, 7, 'success', at='2026-10-10T10:05:00Z')]}
        ci_badge = badges(render(fx, registry, ci))['ci']
        assert R.text_of(R.find(ci_badge, 'span', 'badge-value')) == '2: 1 passed, 0 failed, 0 running, 1 fixed by a later run'
        assert 'badge-fail' not in ci_badge.attrs.get('class', '')
    finally:
        fx.close()


@case
def ci_badge_counts_runs_of_the_active_release():
    fx = fixture()
    try:
        registry = with_rows(fx, rel('DS51', 1, pr=7))
        ci = {'active': [], 'finished': [run(1, 7, 'success'), run(2, 7, 'failure', at='2026-10-10T10:05:00Z'),
                                          run(3, 99, 'failure')]}
        ci['active'].append({'run_id': 4, 'workflow': 'spec-lint', 'why': 'ready PR #7', 'started_at': '2026-10-10T10:10:00Z'})
        out = render(fx, registry, ci)
        ci_badge = badges(out)['ci']
        assert R.text_of(R.find(ci_badge, 'span', 'badge-value')) == '3: 1 passed, 1 failed, 1 running', R.text_of(ci_badge)
        assert 'badge-fail' in ci_badge.attrs['class']
        # the checker does not read ci-runs.json: its CI runs section is the one finding it would raise (R5.51)
        assert [f for f in fx.check(out, 'full-progress', registry=registry) if 'CI runs' not in f[1]] == []
    finally:
        fx.close()


@case
def no_ci_runs_file_means_no_ci_badge():
    fx = fixture()
    try:
        out = render(fx, with_rows(fx, rel('DS51', 1, pr=7)), None)
        assert 'ci' not in badges(out)
        out = render(fx, with_rows(fx, rel('DS51', 1, pr=7)), 'not a dict')
        assert 'ci' not in badges(out)
    finally:
        fx.close()


@case
def release_pr_and_agent_badges_come_from_the_ledger():
    fx = fixture()
    try:
        write_delivery(fx, [train('DS51', 7)], [{'task': 'DS51', 'state': 'running', 'where': 'local'}, {'task': 'DS9', 'state': 'done', 'where': 'cloud'}])
        registry = with_rows(fx, rel('DS51', 1), rel('DS52', 2, status='Live', changed='2026-10-10T09:00+01:00'))
        out = render(fx, registry)
        got = badges(out)
        assert R.text_of(R.find(got['pr'], 'span', 'badge-value')) == '#7'
        assert R.text_of(R.find(got['agents'], 'span', 'badge-value')) == '1 running (1 local, 0 cloud) · 2 total (1 local, 1 cloud)'
        assert R.text_of(R.find(got['release'], 'span', 'badge-value')).startswith('RELEASE-1 · live ~18:00')
        assert R.text_of(R.find(got['last-live'], 'span', 'badge-value')).startswith('RELEASE-2')
    finally:
        fx.close()


@case
def bullet_for_a_failed_release():
    fx = fixture()
    try:
        write_delivery(fx, [train('DS51', 7, hold={'reason': 'waits for the pool', 'by': 'rule', 'until': None})],
                       [{'task': 'DS51', 'state': 'running'}])
        registry = with_rows(fx, rel('DS51', 1))
        ci = {'active': [], 'finished': [run(1, 7, 'failure', job='unit tests')]}
        out = render(fx, registry, ci)
        text = [b for b in bullets(out) if b.startswith('RELEASE-1')][0]
        assert text.startswith('RELEASE-1 (PR #7): CI failed in unit tests.'), text
        assert 'Held: waits for the pool.' in text and 'An agent is running on DS51.' in text, text
        assert 'happen-fail' in out
        assert fx.check(render(fx, registry), 'full-progress', registry=registry) == []
        write_delivery(fx, [train('DS51', 7)], [])
        text = [b for b in bullets(render(fx, registry, ci)) if b.startswith('RELEASE-1')][0]
        assert 'Nothing is running on the fix yet.' in text, text
    finally:
        fx.close()


@case
def bullet_for_a_green_release():
    fx = fixture()
    try:
        write_delivery(fx, [train('DS52', 8, state='cleaned', smoke={'state': 'pass'}, live_at='2026-10-10T10:30:00Z')])
        registry = with_rows(fx, rel('DS52', 2, status='Live', changed='2026-10-10T10:30:00+01:00'))
        out = render(fx, registry, {'active': [], 'finished': [run(1, 8, 'success')]})
        text = [b for b in bullets(out) if b.startswith('RELEASE-2')][0]
        assert text == 'RELEASE-2 (PR #8): CI passed on the first run. Merged green on the first CI run, live 10 Oct 11:30. Smoke test passed.' \
            or ('Merged green on the first CI run, live 10 Oct 11:30.' in text and 'Smoke test passed.' in text), text
        assert 'Not smoke-tested' not in text and 'not cleaned' not in text
        write_delivery(fx, [train('DS52', 8, state='merged')])
        text = [b for b in bullets(render(fx, registry)) if b.startswith('RELEASE-2')][0]
        assert 'Merged, not cleaned up yet.' in text and 'Not smoke-tested.' in text, text
    finally:
        fx.close()


@case
def bullet_when_nothing_is_active():
    fx = fixture()
    try:
        out = render(fx)
        assert bullets(out) == ['No release is active.'], bullets(out)
        assert fx.check(out, 'full-progress') == []
    finally:
        fx.close()


@case
def bullets_name_releases_as_release_n_and_stop_at_eight():
    fx = fixture()
    try:
        trains = [train('DS%d' % (50 + n), 100 + n) for n in range(1, 11)]
        for i, t in enumerate(trains):
            t['id'] = 'T-2026-10-10-%02d' % (i + 1)
        write_delivery(fx, trains)
        registry = with_rows(fx, *[rel('DS%d' % (50 + n), n) for n in range(1, 11)])
        out = render(fx, registry)
        got = bullets(out)
        assert len(got) == 8 and got[-1] == 'And 3 more.', got
        assert all(b.startswith('RELEASE-') for b in got[:-1]), got
        assert 'T-2026' not in ' '.join(got)
        assert fx.check(out, 'full-progress', registry=registry) == []
    finally:
        fx.close()


@case
def check_finds_a_broken_section_zero():
    fx = fixture()
    try:
        out = render(fx)
        assert 'R5.3' in TR.reqs(fx.check(out.replace('class="status-badges"', 'class="x"'), 'full-progress'))
        glance = '<div class="at-a-glance"><p>x</p></div>\n'
        assert 'R5.61' in TR.reqs(fx.check(TR.sub1(out, '<div class="status-badges">', glance + '<div class="status-badges">'), 'full-progress'))
        assert 'R5.61' in TR.reqs(fx.check(TR.sub1(out, '<span class="badge-value">2</span>', '<span class="badge-value">9</span>', 3 if out.count('<span class="badge-value">2</span>') == 3 else out.count('<span class="badge-value">2</span>')), 'full-progress'))
        assert 'R5.62' in TR.reqs(fx.check(out.replace('No release is active.', 'T-2026-10-10-01 is active.'), 'full-progress'))
    finally:
        fx.close()


def main():
    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
            passed += 1
        except Exception:
            failed += 1
            print('FAIL %s' % fn.__name__)
            traceback.print_exc()
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
