#!/usr/bin/env python3
"""DL251: a stale Full Progress lede (it names an older RELEASE-n than the newest Live release) is a warning.

Run:  python -I tools/test_artifacts_dl251.py
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'docs', 'scripts'))
import test_project_artifacts as T

TESTS = []
ENV = None


def case(fn):
    TESTS.append(fn)
    return fn


def project_with(lede):
    """Baseline project: RELEASE-1 is DS1; a second release (RELEASE-2) is made Live; Full Progress gets the lede."""
    p = ENV.baseline()
    p.ok('task-add', '--owner', 'project', '--prefix', 'DS', '--item', 'Second', '--detail', 'Ship.',
         '--expected', '14 Oct', '--release')
    rel2 = [t['id'] for t in p.reg()['tasks'] if t.get('release') == 2][0]
    p.ok('set-task-status', rel2, 'Live')
    d = Path(tempfile.mkdtemp(prefix='dl251-', dir=str(T.TMP)))
    p.ok('export-content', 'full-progress', '--to', d)
    meta = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
    meta['lede'] = lede
    (d / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
    p.ok('edit-content', 'full-progress', '--from', d)
    return p


STALE = 'content/full-progress/meta.json: the lede names RELEASE-1 but RELEASE-2 is live; update it with edit-content'


@case
def old_release_warns():
    r = project_with('RELEASE-1 is live. The next one is building.').run('check')
    assert 'warning  content/full-progress/meta.json: ' + STALE.split(': ', 1)[1] in r.out, r.all


@case
def newest_release_is_quiet():
    r = project_with('RELEASE-2 is live. More follows.').run('check')
    assert 'lede names' not in r.out, r.all


@case
def no_release_name_is_quiet():
    r = project_with('Nothing needs you.').run('check')
    assert 'lede names' not in r.out, r.all


@case
def exit_code_unchanged():
    clean = project_with('RELEASE-2 is live.').run('check')
    stale = project_with('RELEASE-1 is live.').run('check')
    assert clean.code == stale.code, (clean.all, stale.all)


@case
def render_prints_note():
    r = project_with('RELEASE-1 is live.').run('render', '--all')
    assert 'note: content/full-progress/meta.json: the lede names RELEASE-1' in r.out, r.all


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest251-'))
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
