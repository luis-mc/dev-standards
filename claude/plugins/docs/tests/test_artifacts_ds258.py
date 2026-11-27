#!/usr/bin/env python3
"""Tests for DS258 (Full Progress ci-waste badge; R5.64).

Run:  python -I claude/plugins/docs/tests/test_artifacts_ds258.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
import test_artifacts_dl429 as D          # reuses its fixtures and helpers
import render_artifacts as R

TESTS = []


def case(fn):
    TESTS.append(fn)
    return fn


def finished(run_id, why, conclusion, total_s, at):
    return {'run_id': run_id, 'workflow': 'spec-lint', 'conclusion': conclusion, 'why': why,
            'completed_at': at, 'total_s': total_s, 'steps': []}


def waste(ci, live=True):
    fx = D.fixture()
    try:
        rows = [D.rel('DS52', 2, status='Live', pr=7, changed='2026-10-10T09:00+01:00')] if live else []
        registry = D.with_rows(fx, *rows)
        out = D.render(fx, registry, ci)
        got = D.badges(out).get('ci-waste')
        if got is None:
            return None
        assert 'badge-fail' not in got.attrs.get('class', '') and 'badge-alert' not in got.attrs.get('class', '')
        assert [f for f in fx.check(out, 'full-progress', registry=registry) if 'CI runs' not in f[1]] == []
        return R.text_of(R.find(got, 'span', 'badge-value'))
    finally:
        fx.close()


@case
def badge_value_for_a_mixed_set():
    ci = {'active': [], 'finished': [
        finished(1, 'ready PR #7', 'success', 1200, '2026-10-10T10:00:00Z'),
        finished(2, 'ready PR #7', 'failure', 600, '2026-10-10T10:20:00Z'),
        finished(3, 'push', 'cancelled', 300, '2026-10-10T10:30:00Z'),
        finished(4, 'push', 'success', 100, '2026-10-10T10:40:00Z')]}
    assert waste(ci) == '50% green · 30 min per merged PR · 5 min cancelled (7 d)', waste(ci)


@case
def cancelled_minutes_use_the_seven_day_window():
    ci = {'active': [], 'finished': [
        finished(1, 'ready PR #7', 'success', 60, '2026-10-10T10:00:00Z'),
        finished(2, 'push', 'cancelled', 600, '2026-10-01T10:00:00Z'),
        finished(3, 'push', 'cancelled', 120, '2026-10-05T10:00:00Z')]}
    assert waste(ci).endswith('2 min cancelled (7 d)'), waste(ci)


@case
def no_ci_runs_means_no_badge():
    assert waste(None) is None
    assert waste({'active': [], 'finished': []}) is None
    assert waste('not a dict') is None


@case
def no_merged_pr_shows_n_a():
    ci = {'active': [], 'finished': [finished(1, 'ready PR #7', 'success', 600, '2026-10-10T10:00:00Z')]}
    assert waste(ci, live=False) == '100% green · n/a per merged PR · 0 min cancelled (7 d)', waste(ci, live=False)


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
