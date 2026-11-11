#!/usr/bin/env python3
"""DL264: mark-deferred --local accepts the work root, the full-progress folder, or the project folder.

Run:  python -I tools/test_artifacts_dl264.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_project_artifacts as T

TESTS = []
ENV = None
UNTIL = '2026-10-12T00:00:00+00:00'


def case(fn):
    TESTS.append(fn)
    return fn


def check(form):
    p = ENV.baseline()
    root = Path(tempfile.mkdtemp(prefix='dl264w-', dir=str(T.TMP)))
    arg = form(root, p.clone.name)
    r = p.run('mark-deferred', 'full-progress', '--until', UNTIL, '--no-open', '--local', str(arg))
    assert r.code == 0, r.all
    want = root / 'full-progress' / p.clone.name
    lp = Path(p.man()['full_progress_artifact']['local_path'])
    assert lp.is_file() and lp.parent == want, lp
    assert not (root / 'full-progress' / 'full-progress').exists()
    assert not (want / 'full-progress').exists()
    assert str(want) in r.all, r.all


@case
def work_root_form():
    check(lambda root, name: root)


@case
def full_progress_folder_form():
    check(lambda root, name: root / 'full-progress')


@case
def project_folder_form():
    check(lambda root, name: root / 'full-progress' / name)


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest264-'))
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
