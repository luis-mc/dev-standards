#!/usr/bin/env python3
"""DL260: every generated HTML page declares UTF-8 in its first 1024 bytes.

Run:  python -I tools/test_artifacts_dl260.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
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


UNTIL = '2026-10-12T00:00:00+00:00'
META = '<meta charset="utf-8">'


def first_k(path):
    return Path(path).read_bytes()[:1024].decode('utf-8', 'replace')


@case
def repo_copies_declare_utf8():
    p = ENV.baseline()
    pages = sorted(p.rdir.glob('*.html'))
    assert any(x.name.startswith('full-progress') for x in pages) and any(x.name.startswith('feature-') for x in pages)
    for x in pages:
        assert META in first_k(x), x.name


@case
def full_progress_charset_precedes_title():
    p = ENV.baseline()
    fp = [x for x in p.rdir.glob('full-progress*.html')][0]
    assert fp.read_text(encoding='utf-8').startswith(META), fp.name
    assert first_k(fp).index(META) < first_k(fp).index('<title>')


@case
def local_copies_declare_utf8():
    p = ENV.baseline()
    out = Path(tempfile.mkdtemp(prefix='dl260c-', dir=str(T.TMP)))
    p.ok('mark-deferred', 'full-progress', '--until', UNTIL, '--local', str(out), '--no-open')
    pages = [x for x in out.rglob('*.html')]
    assert pages
    for x in pages:
        assert META in first_k(x), x.name


@case
def template_has_charset_first():
    root = Path(HERE).parent / 'claude' / 'plugins' / 'docs' / 'templates'
    assert (root / 'full-progress-artifact.html').read_text(encoding='utf-8').startswith(META)
    assert META in first_k(root / 'feature-artifact.html')


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
