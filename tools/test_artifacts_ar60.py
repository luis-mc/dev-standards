#!/usr/bin/env python3
"""Regression tests for AR60 (the stop state leaves no temp files) and AR61 (the hourly
Full Progress fail-safe applies only while work is open, R9.8, decision D20).

Run:  python -I tools/test_artifacts_ar60.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'docs')
SCRIPTS = os.path.join(PLUGIN, 'scripts')
sys.path.insert(0, SCRIPTS)

import artifact_hourly as H  # noqa: E402
import hook_after_command as A  # noqa: E402
import publish_hourly as PH  # noqa: E402

TESTS = []


def case(fn):
    TESTS.append(fn)
    return fn


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def temps(folder):
    return sorted(n for n in os.listdir(folder) if n.endswith('.tmp'))


@case
def ar60_write_state_leaves_no_temp_file():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, '.claude', 'artifacts-stop-state.json')
        A.write_state(path, {'a': 1})
        assert A.read_state(path) == {'a': 1}
        assert temps(os.path.dirname(path)) == []


@case
def ar60_failed_replace_removes_its_temp_and_does_not_raise():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, '.claude', 'artifacts-stop-state.json')
        A.write_state(path, {'a': 1})
        real, calls = os.replace, []

        def held(src, dst):
            calls.append(src)
            raise PermissionError(13, 'held by another process')
        A.os.replace = held
        try:
            A.write_state(path, {'a': 2})          # warns, never raises
        finally:
            A.os.replace = real
        assert len(calls) == A.REPLACE_TRIES, calls
        assert temps(os.path.dirname(path)) == [], temps(os.path.dirname(path))
        assert A.read_state(path) == {'a': 1}      # the old state is kept


@case
def ar60_a_short_hold_is_retried():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, '.claude', 'artifacts-stop-state.json')
        real, calls = os.replace, []

        def held_once(src, dst):
            calls.append(src)
            if len(calls) == 1:
                raise PermissionError(13, 'held')
            return real(src, dst)
        A.os.replace = held_once
        try:
            A.write_state(path, {'b': 1})
        finally:
            A.os.replace = real
        assert A.read_state(path) == {'b': 1} and len(calls) == 2


@case
def ar60_stale_temps_are_swept_fresh_ones_kept():
    with tempfile.TemporaryDirectory() as root:
        folder = os.path.join(root, '.claude')
        os.makedirs(folder)
        path = os.path.join(folder, 'artifacts-stop-state.json')
        old = path + '.27424.tmp'
        fresh = path + '.46968.tmp'
        other = os.path.join(folder, 'something-else.json.1.tmp')
        for p in (old, fresh, other):
            with open(p, 'w') as f:
                f.write('{}')
        past = time.time() - A.STALE_TEMP_SECONDS - 30
        os.utime(old, (past, past))
        os.utime(other, (past, past))
        A.write_state(path, {'c': 1})
        names = temps(folder)
        assert os.path.basename(old) not in names, names          # stale: swept
        assert os.path.basename(fresh) in names, names            # may belong to a running hook
        assert os.path.basename(other) in names, names            # not ours


PUBLISHED = {'full_progress_artifact': {'url': 'u', 'published_at': '2026-11-07T00:00:00+00:00'}}
LATER = utc(2026, 11, 7, 1, 30)       # 90 minutes after the publish


@case
def ar61_hourly_is_due_only_while_work_is_open():
    for status in ('Running', 'Waiting', 'Needs you'):
        assert H.hourly_due(PUBLISHED, LATER, [{'id': 'X1', 'status': status}]) == 90, status
    for status in ('Live', 'Built', 'To do', 'On hold', 'Dropped', 'Failed'):
        assert H.hourly_due(PUBLISHED, LATER, [{'id': 'X1', 'status': status}]) is None, status
    assert H.hourly_due(PUBLISHED, LATER, []) is None
    assert H.hourly_due(PUBLISHED, LATER) == 90                 # no registry given: no open-work test


@case
def ar61_publish_hourly_is_silent_with_no_open_work():
    idle = [{'id': 'X1', 'status': 'Live'}, {'id': 'X2', 'status': 'To do'}]
    assert PH.reasons(PUBLISHED, idle, LATER) == []
    busy = idle + [{'id': 'X3', 'status': 'Running'}]
    why = PH.reasons(PUBLISHED, busy, LATER)
    assert why and 'hourly fail-safe' in why[0], why
    # a release change is still published at once, open work or not (R9.9)
    rel = [{'id': 'X4', 'status': 'Live', 'release': 3, 'changed': '2026-11-07T00:30:00+00:00'}]
    assert any('release task X4' in r for r in PH.reasons(PUBLISHED, rel, LATER))


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
