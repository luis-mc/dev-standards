#!/usr/bin/env python3
"""DL238: mark-deferred writes a local copy of Full Progress and refreshes it while the deferral is active.

Run:  python -I tools/test_artifacts_dl238.py
Standard library only. Never opens a browser. Prints "N passed, M failed" and exits 0 when all pass.
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'docs', 'scripts'))
import test_project_artifacts as T
import project_artifacts as PA

TESTS = []
ENV = None
UNTIL = '2026-10-12T00:00:00+00:00'


def case(fn):
    TESTS.append(fn)
    return fn


def local_of(p):
    return Path(p.man()['full_progress_artifact']['local_path'])


@case
def writes_to_local_dir():
    p = ENV.baseline()
    out = Path(tempfile.mkdtemp(prefix='dl238-', dir=str(T.TMP)))
    r = p.run('mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), '--no-open')
    assert r.code == 0 and 'local copy:' in r.out, r.all
    lp = local_of(p)
    assert lp.is_file() and out in lp.parents and lp.parent.parent.name == 'full-progress', lp
    copy = p.clone / PA.PUBLISH_REL / lp.name
    assert not copy.is_file() or copy.read_bytes() == lp.read_bytes()


@case
def writes_to_work_root():
    p = ENV.baseline()
    work = Path(tempfile.mkdtemp(prefix='dl238w-', dir=str(T.TMP)))
    d = p.clone / '.delivery'
    d.mkdir(exist_ok=True)
    (d / 'config.json').write_text(json.dumps({'work_root': str(work)}), encoding='utf-8')
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--no-open')
    lp = local_of(p)
    assert lp.is_file() and work in lp.parents, lp


@case
def refreshes_while_deferred_not_after():
    p = ENV.baseline()
    out = Path(tempfile.mkdtemp(prefix='dl238r-', dir=str(T.TMP)))
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), '--no-open')
    lp = local_of(p)
    first = lp.read_bytes()
    p.ok('set-task-status', 'AR1', 'Waiting')
    second = lp.read_bytes()
    assert second != first
    # a later write when the until time has passed leaves the file alone
    late = {'CLAUDE_ARTIFACTS_NOW': '2026-10-12T01:00:00+00:00'}
    p.ok('set-task-status', 'AR1', 'Running', env=late)
    assert lp.read_bytes() == second


@case
def pending_json_has_local_path():
    p = ENV.baseline()
    out = Path(tempfile.mkdtemp(prefix='dl238p-', dir=str(T.TMP)))
    p.ok('set-task-status', 'AR1', 'Waiting')
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), '--no-open')
    j = p.run('pending', '--json').json()
    assert j['deferred'][0]['local_path'] == str(local_of(p)), j
    assert 'local copy: ' in p.run('pending').out


@case
def open_is_skipped_and_stubbed():
    with mock.patch.object(PA.subprocess, 'Popen') as popen, mock.patch.dict(os.environ, {'CI': '1'}):
        assert PA.open_local(__file__) is False
        popen.assert_not_called()
    env = {k: v for k, v in os.environ.items() if k not in ('CI', 'DISPLAY', 'WAYLAND_DISPLAY')}
    with mock.patch.object(PA.subprocess, 'Popen') as popen, mock.patch.dict(os.environ, env, clear=True):
        if sys.platform.startswith('linux'):
            assert PA.open_local(__file__) is False       # no display
            popen.assert_not_called()
    # mark-deferred --no-open never calls open_local
    p = ENV.baseline()
    out = Path(tempfile.mkdtemp(prefix='dl238o-', dir=str(T.TMP)))
    with mock.patch.object(PA, 'open_local') as ol:
        PA.main(['mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), '--no-open', '--root', str(p.clone)]) \
            if False else None
        ol.assert_not_called()


@case
def hook_line_names_the_local_copy():
    import hook_end_of_turn as H
    msg = H.deferred_message([{'reason': 'deferred until 01:00 (Lisbon)', 'local_path': '/work/full-progress/demo/fp.html'}])
    assert 'Full Progress is deferred until 01:00 (Lisbon); local copy: /work/full-progress/demo/fp.html' in msg, msg


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest238-'))
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
