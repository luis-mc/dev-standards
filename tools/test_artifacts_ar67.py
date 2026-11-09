#!/usr/bin/env python3
"""Regression tests for AR67 (`pending --refresh` renders first, so mark-published accepts the publish).

Run:  python -I tools/test_artifacts_ar67.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'artifacts', 'scripts'))
import test_project_artifacts as T          # the throwaway-repository harness

TESTS = []
URL = 'https://claude.ai/artifact/ccc'
ENV = None


def case(fn):
    TESTS.append(fn)
    return fn


@case
def ar67_pending_refresh_then_mark_published():
    p = ENV.baseline()
    p.run('pending', '--json')
    p.ok('mark-published', 'full-progress', '--url', URL)
    p.ok('task-add', '--owner', 'artifacts', '--item', 'New', '--detail', 'd', '--expected', '15 Oct')
    p.run('pending', '--json', '--refresh')          # renders first, writes the publish copy
    # (the publish with the Artifact tool happens here)
    r = p.run('mark-published', 'full-progress', '--url', URL)
    assert r.code == 0, r.all
    assert 'differs from a fresh render' not in r.all, r.all


@case
def ar67_refresh_twice_still_marks_published():
    p = ENV.baseline()
    p.run('pending', '--json', '--refresh')
    p.run('pending', '--json', '--refresh')
    r = p.run('mark-published', 'full-progress', '--url', URL)
    assert r.code == 0, r.all


@case
def ar67_refusal_names_the_next_command():
    from project_artifacts import cmd_mark_published
    import inspect
    assert 'pending --json --refresh' in inspect.getsource(cmd_mark_published)


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest67-'))
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
