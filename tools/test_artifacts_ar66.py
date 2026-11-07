#!/usr/bin/env python3
"""Regression tests for AR66 (a release with no Expected is headed `RELEASE-<n> · not scheduled`, R5.46).

Run:  python -I tools/test_artifacts_ar66.py
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'artifacts', 'scripts'))
import test_project_artifacts as T          # the throwaway-repository harness
import hook_end_of_turn as HOOK
import render_artifacts as RA

TESTS = []
URL = 'https://claude.ai/artifact/ccc'


def case(fn):
    TESTS.append(fn)
    return fn


@case
def ar66_release_without_expected_is_added_and_headed_not_scheduled():
    p = ENV.baseline()
    r = p.run('task-add', '--owner', 'artifacts', '--item', 'R', '--detail', 'd', '--release', '--status', 'To do')
    assert r.code == 0, r.all
    assert p.run('check').code == 0, p.run('check').all
    text = ''.join(f.read_text(encoding='utf-8') for f in (p.clone / 'docs' / 'artifacts').glob('full-progress*.html'))
    assert 'RELEASE-' in text and ' · not scheduled' in text, 'heading missing'


@case
def ar66_release_with_expected_keeps_its_heading():
    p = ENV.baseline()
    r = p.run('task-add', '--owner', 'artifacts', '--item', 'R', '--detail', 'd', '--release', '--status', 'To do',
              '--expected', '12 Oct ~11:00')
    assert r.code == 0, r.all
    assert p.run('check').code == 0, p.run('check').all
    text = ''.join(f.read_text(encoding='utf-8') for f in (p.clone / 'docs' / 'artifacts').glob('full-progress*.html'))
    assert ' · live ~11:00' in text and ' · not scheduled' not in text, 'heading changed'


@case
def ar66_heading_has_no_stray_whitespace():
    from datetime import datetime
    for exp in ('', '  ', ' 12 Oct '):
        h = RA._release_heading({'id': 'X1', 'item': 'r', 'release': 7, 'expected': exp}, datetime(2026, 10, 10), [])
        assert h == ' '.join(h.split()), repr(h)


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest66-'))
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
