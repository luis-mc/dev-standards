#!/usr/bin/env python3
"""DL269: task-add and set-task-status refuse U+FFFD; check flags one already held.

Run:  python -I tools/test_artifacts_dl269.py
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
import test_project_artifacts as T

TESTS = []
ENV = None
BAD = 'lost � char'


def case(fn):
    TESTS.append(fn)
    return fn


@case
def task_add_refuses_in_detail():
    p = ENV.baseline()
    before = p.reg()
    r = p.run('task-add', '--owner', 'site', '--item', 'New', '--detail', BAD, '--expected', '14 Oct')
    assert r.code != 0, r.all
    assert '--detail has the replacement character U+FFFD at position 5' in r.all, r.all
    assert p.reg() == before


@case
def set_task_status_refuses_in_item():
    p = ENV.baseline()
    before = p.reg()
    r = p.run('set-task-status', 'SI1', 'To do', '--item', BAD)
    assert r.code != 0, r.all
    assert '--item has the replacement character U+FFFD' in r.all, r.all
    assert p.reg() == before


@case
def set_task_status_refuses_in_history():
    p = ENV.baseline()
    r = p.run('set-task-status', 'SI1', 'To do', '--history', BAD)
    assert r.code != 0 and '--history' in r.all, r.all


@case
def accents_still_pass():
    p = ENV.baseline()
    p.ok('task-add', '--owner', 'site', '--item', 'Café – naïve 日本語', '--detail', 'Ação “quoted” ü',
         '--expected', '14 Oct')
    p.ok('set-task-status', 'SI1', 'To do', '--detail', 'Ñandú ✓')


@case
def check_flags_existing():
    p = ENV.baseline()
    path = p.clone / 'docs' / 'artifacts' / 'registry.json'
    reg = json.loads(path.read_text(encoding='utf-8'))
    reg['tasks'][1]['detail'] = BAD
    path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    r = p.run('check')
    assert r.code != 0, r.all
    assert 'U+FFFD' in r.all and 'field detail' in r.all and reg['tasks'][1]['id'] in r.all, r.all


@case
def check_clean_without_it():
    p = ENV.baseline()
    r = p.run('check')
    assert 'U+FFFD' not in r.all, r.all


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest269-'))
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
