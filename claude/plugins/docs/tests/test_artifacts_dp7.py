#!/usr/bin/env python3
"""DP7 (decision D2): a default Expected by task type, and the overdue sweep.

Run:  python -I claude/plugins/docs/tests/test_artifacts_dp7.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
import test_project_artifacts as T          # the throwaway-repository harness
import artifact_hourly as H

TESTS = []
NOW = {'CLAUDE_ARTIFACTS_NOW': '2026-10-14T10:02:00+01:00'}


def case(fn):
    TESTS.append(fn)
    return fn


@case
def dp7_default_eta_table_and_format():
    assert H.default_eta_minutes('agent') == 15 and H.default_eta_minutes('ci') == 5
    assert H.default_eta_minutes('nonsense') == H.default_eta_minutes(None) == 30
    got = H.default_expected({'timezone': 'Europe/Lisbon'}, 'agent', H.parse_iso('2026-10-14T10:02:00+01:00'))
    assert got == '14 Oct ~10:20', got            # 10:02 + 15 min, rounded up to 10:20
    assert H.EXPECTED_RE.match(got)


@case
def dp7_task_add_without_expected_takes_the_default_for_its_type():
    p = ENV.baseline()
    a = p.ok('task-add', '--owner', 'artifacts', '--item', 'A', '--detail', 'd', '--status', 'Running',
             '--type', 'agent', '--rides', 'RELEASE-1', env=NOW).out.strip()
    b = p.ok('task-add', '--owner', 'artifacts', '--item', 'B', '--detail', 'd', '--status', 'Running',
             '--rides', 'RELEASE-1', env=NOW).out.strip()
    assert p.task(a)['expected'] == '14 Oct ~10:20', p.task(a)
    assert p.task(b)['expected'] == '14 Oct ~10:35', p.task(b)         # type other: 30 min
    assert 'default ETA' in p.task(a)['expected_basis'], p.task(a)
    c = p.ok('task-add', '--owner', 'artifacts', '--item', 'C', '--detail', 'd', '--status', 'Running',
             '--expected', '14 Oct ~18:00', '--rides', 'RELEASE-1', env=NOW).out.strip()
    assert p.task(c)['expected'] == '14 Oct ~18:00'                     # an explicit --expected wins
    assert p.run('check').code == 0, p.run('check').all


@case
def dp7_set_task_status_running_without_expected_takes_the_default():
    p = ENV.baseline()
    t = p.ok('task-add', '--owner', 'artifacts', '--item', 'T', '--detail', 'd').out.strip()     # To do, Not scheduled
    p.ok('set-task-status', t, 'Running', '--type', 'ci', '--rides', 'RELEASE-1', env=NOW)
    assert p.task(t)['expected'] == '14 Oct ~10:10', p.task(t)


@case
def dp7_overdue_sweep_moves_only_rows_over_an_hour_past_due():
    p = ENV.baseline()
    p.ok('set-task-status', 'AR1', 'Running', '--expected', '14 Oct ~08:00', '--rides', 'RELEASE-1', env=NOW)
    p.ok('set-task-status', 'SI1', 'Running', '--expected', '14 Oct ~09:30', '--rides', 'RELEASE-1', env=NOW)
    r = p.ok('overdue-sweep', env=NOW)
    assert p.task('AR1')['status'] == 'Needs you', p.task('AR1')
    assert p.task('SI1')['status'] == 'Running', p.task('SI1')
    assert 'AR1' in r.all and 'SI1' not in r.all, r.all
    again = p.run('overdue-sweep', env=NOW)
    assert again.code == 0 and 'no row' in again.all, again.all


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptestdp7-'))
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
