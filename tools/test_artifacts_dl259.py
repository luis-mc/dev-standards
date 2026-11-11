#!/usr/bin/env python3
"""DL259: a project design file is checked against the accents contract (neutral and size tokens optional).

Run:  python -I tools/test_artifacts_dl259.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'docs', 'scripts'))
import test_project_artifacts as T
import render_artifacts as R

TESTS = []
ENV = None
N = [0]


def case(fn):
    TESTS.append(fn)
    return fn


def default_css():
    return (T.REAL_PLUGIN / 'design' / 'default-design.css').read_text(encoding='utf-8')


def strip_tokens(css, names):
    """Remove every declaration of the named tokens, in every block."""
    for name in names:
        css = re.sub(r'(?<![\w-])%s\s*:[^;}]*;?' % re.escape(name), '', css)
    return css


def write(css):
    N[0] += 1
    f = T.TMP / ('dl259-%d.css' % N[0])
    f.write_text(css, encoding='utf-8')
    return f


@case
def accents_only_file_is_accepted_and_clean():
    p = ENV.baseline()
    css = strip_tokens(default_css(), R.NEUTRAL_TOKENS)
    assert not R.ignored_tokens(css)
    r = p.ok('design', 'set', write(css))
    assert p.man()['design'] == 'design.css', r.all
    c = p.run('check')
    assert 'R5.11' not in c.all and 'ignored (accents only)' not in c.all, c.all


@case
def neutral_tokens_are_accepted_with_warning():
    p = ENV.baseline()
    r = p.ok('design', 'set', write(default_css()))
    assert 'ignored (accents only)' in r.all, r.all
    assert p.man()['design'] == 'design.css'


@case
def missing_accent_token_is_refused_and_named():
    p = ENV.baseline()
    css = strip_tokens(default_css(), ['--signal'])
    before = p.head()
    r = p.run('design', 'set', write(css))
    assert r.code == 1 and 'token contract' in r.err and '--signal' in r.err, r.err
    assert p.head() == before and p.man()['design'] == 'default'


@case
def missing_dark_accent_is_refused():
    css = default_css()
    cut = css.index('[data-theme="dark"]')
    css = css[:cut] + strip_tokens(css[cut:], ['--failed'])
    probs = R.check_tokens(css, accents_only=True)
    assert any('--failed' in x and 'dark' in x for x in probs), probs


@case
def default_keeps_the_full_contract():
    css = default_css()
    assert R.check_tokens(css) == []
    assert R.check_tokens(css, accents_only=True) == []
    stripped = strip_tokens(css, R.NEUTRAL_TOKENS)
    assert R.check_tokens(stripped)                      # full contract still wants them
    assert R.check_tokens(stripped, accents_only=True) == []
    assert not set(R.accent_tokens()) & set(R.NEUTRAL_TOKENS)


@case
def own_design_problems_uses_accents_contract():
    d = Path(tempfile.mkdtemp(prefix='dl259-rec-', dir=str(T.TMP)))
    (d / 'design.css').write_text(strip_tokens(default_css(), R.NEUTRAL_TOKENS), encoding='utf-8')
    assert R.own_design_problems({'design': 'design.css'}, str(d)) == []
    (d / 'design.css').write_text(strip_tokens(default_css(), ['--live']), encoding='utf-8')
    probs = R.own_design_problems({'design': 'design.css'}, str(d))
    assert probs and all('--live' in x or '--on-live' not in x for x in probs), probs


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest259-'))
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
