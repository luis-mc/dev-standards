#!/usr/bin/env python3
"""DL246: the local Full Progress page: where it goes, what is copied, refresh, and opening once.

Run:  python -I tools/test_artifacts_dl246.py
Standard library only. Never opens a real browser: the opener is a stub script on PATH (Linux) or the case is skipped.
Prints "N passed, M failed" and exits 0 when all pass.
"""
import json
import os
import re
import stat
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
TAG = '<meta http-equiv="refresh" content="60">'


def case(fn):
    TESTS.append(fn)
    return fn


def tmpdir(prefix):
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(T.TMP)))


def machine(work_root):
    d = tmpdir('dl246m-')
    if work_root is not None:
        (d / 'machine.json').write_text(json.dumps({'work_root': str(work_root)}), encoding='utf-8')
    return {'DELIVERY_MACHINE_DIR': str(d)}


def local_of(p):
    return Path(p.man()['full_progress_artifact']['local_path'])


@case
def machine_work_root_used_when_project_sets_none():
    p = ENV.baseline()
    root = tmpdir('dl246w-')
    r = p.run('mark-deferred', 'full-progress', '--until', UNTIL, '--no-open', env=machine(root))
    assert r.code == 0, r.all
    lp = local_of(p)
    assert lp.is_file() and lp.parent == root / 'full-progress' / p.clone.name, lp


@case
def project_work_root_wins_over_machine():
    p = ENV.baseline()
    mine, theirs = tmpdir('dl246a-'), tmpdir('dl246b-')
    d = p.clone / '.delivery'
    d.mkdir(exist_ok=True)
    (d / 'config.json').write_text(json.dumps({'work_root': str(mine)}), encoding='utf-8')
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--no-open', env=machine(theirs))
    assert mine in local_of(p).parents and not (theirs / 'full-progress').exists()


@case
def fallback_warns_and_names_machine_json():
    p = ENV.baseline()
    r = p.run('mark-deferred', 'full-progress', '--until', UNTIL, '--no-open', env=machine(None))
    assert r.code == 0, r.all
    assert 'work_root' in r.err and 'machine.json' in r.err, r.err
    assert str(p.clone / T_PUBLISH) in str(local_of(p)), local_of(p)


T_PUBLISH = os.path.join('.claude', 'artifacts-publish')


@case
def copy_is_repo_copy_with_feature_pages_and_links_resolve():
    p = ENV.baseline()
    out = tmpdir('dl246c-')
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), '--no-open')
    lp = local_of(p)
    repo = p.rdir / lp.name
    assert lp.read_text(encoding='utf-8').replace(TAG, '', 1) == repo.read_text(encoding='utf-8')
    feats = sorted(x.name for x in p.rdir.glob('feature-*.html'))
    assert feats, 'the sample record has no feature pages'
    for name in feats:
        assert (lp.parent / name).is_file(), name
    links = set(re.findall(r'href="(feature-[^"#]+\.html)', lp.read_text(encoding='utf-8')))
    assert links, 'Full Progress links no feature page'
    for l in links:
        assert (lp.parent / l).is_file(), l


@case
def refresh_tag_only_in_local_copies():
    p = ENV.baseline()
    out = tmpdir('dl246t-')
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), '--no-open')
    p.ok('set-task-status', 'AR1', 'Waiting')
    lp = local_of(p)
    for f in lp.parent.glob('*.html'):
        assert f.read_text(encoding='utf-8').count(TAG) == 1, f
    for f in p.rdir.glob('*.html'):
        assert TAG not in f.read_text(encoding='utf-8'), f
    pub = p.clone / T_PUBLISH
    for f in pub.glob('*.html') if pub.is_dir() else []:
        assert TAG not in f.read_text(encoding='utf-8'), f


@case
def opened_once_across_two_deferrals_and_refreshes():
    if not sys.platform.startswith('linux'):
        return
    p = ENV.baseline()
    out, bin_dir = tmpdir('dl246o-'), tmpdir('dl246bin-')
    log = bin_dir / 'opened.log'
    stub = bin_dir / 'xdg-open'
    stub.write_text('#!/bin/sh\necho "$1" >> "%s"\n' % log, encoding='utf-8')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {'PATH': str(bin_dir) + os.pathsep + os.environ.get('PATH', ''), 'DISPLAY': ':99'}
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), env=env)
    p.ok('set-task-status', 'AR1', 'Waiting', env=env)
    p.ok('mark-deferred', 'full-progress', '--until', '2026-10-12T02:00:00+00:00', '--local', str(out), env=env)
    p.ok('set-task-status', 'AR1', 'Running', env=env)
    import time
    for _ in range(20):                      # the stub runs detached
        if log.is_file():
            break
        time.sleep(0.1)
    time.sleep(0.3)
    lines = log.read_text(encoding='utf-8').split() if log.is_file() else []
    assert len(lines) == 1, lines
    assert p.man()['full_progress_artifact'].get('local_opened') is True


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest246-'))
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
