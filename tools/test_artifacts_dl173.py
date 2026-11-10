#!/usr/bin/env python3
"""DL173: the artifacts readers check the schema of the delivery ledger and ci-runs file.

Run:  python -I tools/test_artifacts_dl173.py
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'artifacts', 'scripts'))
import test_project_artifacts as T
import project_artifacts as PA

TESTS = []
ENV = None


def case(fn):
    TESTS.append(fn)
    return fn


def fresh(files):
    """A temp root holding .delivery/<name>: <text> for each entry; clears recorded warnings."""
    root = Path(tempfile.mkdtemp(prefix='dl173-', dir=str(T.TMP)))
    (root / '.delivery').mkdir()
    for name, data in files.items():
        (root / '.delivery' / name).write_text(json.dumps(data), encoding='utf-8')
    del PA._SCHEMA_WARNINGS[:]
    return root


@case
def ledger_current_schema_is_read():
    root = fresh({'ledger.json': {'schema': 1, 'trains': [{'release_no': 4}]}})
    assert PA.ledger_release_numbers(root) == {4}
    assert PA.schema_warnings(root) == []


@case
def ledger_missing_schema_warns():
    root = fresh({'ledger.json': {'trains': [{'release_no': 4}]}})
    assert PA.ledger_release_numbers(root) == set()
    w = PA.schema_warnings(root)
    assert len(w) == 1 and 'ledger' in w[0] and 'no usable schema' in w[0], w


@case
def ledger_newer_schema_warns_once():
    root = fresh({'ledger.json': {'schema': 3, 'trains': [{'release_no': 4}]}})
    assert PA.ledger_release_numbers(root) == set()
    assert PA.ledger_release_numbers(root) == set()
    w = PA.schema_warnings(root)
    assert w == ['delivery ledger schema 3 is newer than this reader (1): update luismc-artifacts'], w


@case
def ledger_older_schema_is_read():
    old = PA.LEDGER_SCHEMA
    PA.LEDGER_SCHEMA = 2
    try:
        root = fresh({'ledger.json': {'schema': 1, 'trains': [{'release_no': 2}]}})
        assert PA.ledger_release_numbers(root) == {2}
        assert PA.schema_warnings(root) == []
    finally:
        PA.LEDGER_SCHEMA = old


@case
def absent_files_stay_silent():
    root = fresh({})
    assert PA.ledger_release_numbers(root) == set()
    assert PA.read_ci_runs(root) is None
    assert PA.schema_warnings(root) == []


@case
def ci_runs_newer_schema_warns_and_returns_none():
    root = fresh({'ci-runs.json': {'schema': 9, 'runs': []}})
    assert PA.read_ci_runs(root) is None
    w = PA.schema_warnings(root)
    assert len(w) == 1 and 'ci-runs schema 9 is newer' in w[0], w


@case
def ci_runs_without_schema_still_reads():
    root = fresh({'ci-runs.json': {'runs': []}})
    assert PA.read_ci_runs(root) == {'runs': []}
    assert PA.schema_warnings(root) == []


@case
def check_and_pending_print_the_warning():
    p = ENV.baseline()
    d = p.clone / '.delivery'
    d.mkdir(exist_ok=True)
    (d / 'ledger.json').write_text(json.dumps({'schema': 7, 'trains': []}), encoding='utf-8')
    for cmd in ('check', 'pending'):
        r = p.run(cmd)
        assert 'ledger schema 7 is newer than this reader' in r.all, (cmd, r.all)
    r = p.run('pending', '--json')
    assert '"warnings"' in r.all, r.all


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest173-'))
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
