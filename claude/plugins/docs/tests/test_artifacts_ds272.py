#!/usr/bin/env python3
"""Tests for DS272 (Full Progress links every pull request number; R5.65, R5.66).

Run:  python -I claude/plugins/docs/tests/test_artifacts_ds272.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import copy
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
import test_artifacts_dl429 as D          # reuses its fixtures and helpers
import test_render_artifacts as TR
import test_project_artifacts as T          # the throwaway-repository harness
import render_artifacts as R
import pr_links as P

TESTS = []
GH = {'provider': 'github', 'repo': 'acme-co/widgets'}
GL = {'provider': 'gitlab', 'repo': 'acme-co/team/widgets', 'host': 'git.acme.example'}


def case(fn):
    TESTS.append(fn)
    return fn


def page(setting):
    """A Full Progress page with two releases on carrier PR 298 and one on PR 301."""
    fx = D.fixture()
    try:
        fx.manifest = copy.deepcopy(fx.manifest)
        if setting is not None:
            fx.manifest['pr_links'] = setting
        D.write_delivery(fx, [D.train('DS51', 298), D.train('DS53', 301)])
        registry = D.with_rows(fx, D.rel('DS51', 1, pr=298), D.rel('DS52', 2, pr=298),
                               D.rel('DS53', 3, pr=301), D.rel('DS54', 4, status='Live', pr=250, changed='2026-10-10T09:00+01:00'))
        out = D.render(fx, registry)
        again = D.render(fx, registry)
        return out, again, fx.check(out, 'full-progress', registry=registry)
    finally:
        fx.close()


def anchors(out):
    return re.findall(r'<a href="([^"]*)" target="_blank" rel="noopener noreferrer">([^<]*)</a>', out)


@case
def github_and_gitlab_urls():
    assert P.pr_url(GH, 298) == 'https://github.com/acme-co/widgets/pull/298'
    assert P.pr_url({'provider': 'github', 'repo': 'a/b', 'host': 'ghe.acme.example'}, 5) == 'https://ghe.acme.example/a/b/pull/5'
    assert P.pr_url(GL, 7) == 'https://git.acme.example/acme-co/team/widgets/-/merge_requests/7'
    assert P.pr_url({'provider': 'gitlab', 'repo': 'g/p'}, 7) == 'https://gitlab.com/g/p/-/merge_requests/7'
    assert P.pr_url(GH, 0) is None and P.pr_url(GH, '298') is None and P.pr_url(GH, True) is None


@case
def ssh_and_https_remotes_parse():
    want = {'provider': 'github', 'repo': 'acme-co/widgets'}
    for url in ('git@github.com:acme-co/widgets.git', 'https://github.com/acme-co/widgets.git', 'https://github.com/acme-co/widgets',
                'ssh://git@github.com/acme-co/widgets.git', 'https://user@github.com/acme-co/widgets/'):
        assert P.parse_remote(url) == want, url
    assert P.parse_remote('git@gitlab.com:g/sub/p.git') == {'provider': 'gitlab', 'repo': 'g/sub/p'}
    assert P.parse_remote('git@git.acme.example:g/p.git') is None            # not a known provider
    assert P.parse_remote('git@gitlab.acme.example:g/p.git') == {'provider': 'gitlab', 'repo': 'g/p', 'host': 'gitlab.acme.example'}
    assert P.parse_remote('') is None and P.parse_remote('/local/path') is None and P.parse_remote('https://github.com/solo') is None


@case
def custom_template_needs_n_and_https():
    ok = {'provider': 'custom', 'template': 'https://review.acme.example/changes/{n}'}
    assert P.pr_url(ok, 12) == 'https://review.acme.example/changes/12'
    assert P.pr_url({'provider': 'custom', 'template': 'https://review.acme.example/changes'}, 12) is None
    assert P.problems({'provider': 'custom', 'template': 'https://review.acme.example/changes'})


@case
def only_https_is_linked():
    for bad in ('javascript:alert({n})', 'data:text/html,{n}', 'http://review.acme.example/{n}', 'HTTP://x/{n}',
                'https://x.example/{n} onclick=1', 'https://x.example/"{n}', 'https://x.example/<{n}>', '//x.example/{n}'):
        s = {'provider': 'custom', 'template': bad}
        assert P.pr_url(s, 3) is None, bad
        assert P.link('PR 3', 3, s) == 'PR 3', bad


@case
def values_are_escaped_and_bad_values_refused():
    assert P.link('PR <3>', 3, GH).count('<3>') == 0
    for bad in ({'provider': 'github', 'repo': 'a/b"><script>'}, {'provider': 'github', 'repo': 'a b/c'},
                {'provider': 'github', 'repo': 'a/b', 'host': 'x.example/evil'}, {'provider': 'github', 'repo': 'a'},
                {'provider': 'ftp', 'repo': 'a/b'}, {'provider': 'github', 'repo': 'a/b', 'template': 'https://x/{n}'}, 'x', None):
        assert P.problems(bad), bad
        assert P.pr_url(bad, 3) is None, bad
    # a template with an ampersand is escaped in the attribute
    s = {'provider': 'custom', 'template': 'https://x.example/q?a=1&b={n}'}
    assert 'href="https://x.example/q?a=1&amp;b=3"' in P.link('PR 3', 3, s)


@case
def absent_setting_gives_plain_text():
    out, _again, found = page(None)
    assert '<a href="https://github.com' not in out and 'target="_blank"' not in out
    assert 'PR 298' in out and '#298' in out and '(PR #298)' in out
    assert found == [], found


@case
def rendering_is_deterministic():
    for setting in (None, GH, GL):
        out, again, _ = page(setting)
        assert out == again


@case
def every_pr_label_is_a_link_with_target_and_rel():
    out, _again, found = page(GH)
    assert found == [], found
    links = anchors(out)
    assert links, 'no link found'
    for href, text in links:
        n = re.search(r'(\d+)$', text).group(1)
        assert href == 'https://github.com/acme-co/widgets/pull/' + n, (href, text)
    shown = {t for _, t in links}
    for want in ('PR 298', 'PR 301', 'PR #298', 'PR #301', '#298', '#301'):
        assert want in shown, (want, sorted(shown))
    # no PR label is left outside an anchor
    bare = re.sub(r'<a href="[^"]*" target="_blank" rel="noopener noreferrer">[^<]*</a>', '', out)
    bare = re.sub(r'<title>.*?</title>|<script.*?</script>|<style.*?</style>', '', bare, flags=re.S)
    bare = re.sub(r'aria-label="[^"]*"|data-[a-z-]+="[^"]*"', '', bare)
    for m in re.finditer(r'(?:\bPR #?|#)(29[0-9]|30[0-9])(?!\d)', bare):
        raise AssertionError('PR label without a link: ' + bare[max(0, m.start() - 40):m.end() + 20])
    # the published-page rule: nothing but https links to the provider
    assert not re.search(r'href="(?!https://|#|\.|file:)', ''.join('href="%s"' % h for h, _ in links))


@case
def gitlab_page_uses_merge_request_urls():
    out, _again, found = page(GL)
    assert found == [], found
    assert 'href="https://git.acme.example/acme-co/team/widgets/-/merge_requests/298"' in out


@case
def bullet_head_is_linked_and_the_rest_is_text():
    html = R._happening_html([('happen-ok', 'RELEASE-197 (PR #296): CI passed <b>.')], GH)
    assert '(<a href="https://github.com/acme-co/widgets/pull/296" target="_blank" rel="noopener noreferrer">PR #296</a>):' in html
    assert '&lt;b&gt;' in html
    assert 'href' not in R._happening_html([('happen-ok', 'RELEASE-197 (PR #296): ok.')], None)


ENV = None


def git_in(p, *a):
    T.git(p.clone, *a, check=False)


@case
def render_derives_the_setting_from_the_remote_and_writes_it():
    p = ENV.baseline()
    assert 'pr_links' not in p.man()
    git_in(p, 'remote', 'set-url', 'origin', 'git@github.com:acme-co/widgets.git')
    p.ok('render', '--all')
    assert p.man()['pr_links'] == GH, p.man().get('pr_links')
    assert p.ok('check').code == 0


@case
def a_remote_that_is_not_known_leaves_plain_text():
    p = ENV.baseline()
    git_in(p, 'remote', 'set-url', 'origin', '/srv/local/remote.git')
    p.ok('render', '--all')
    assert 'pr_links' not in p.man()
    fp = [f for f in p.rdir.glob('*.html') if 'full-progress' in f.name]
    assert fp and all('target="_blank"' not in f.read_text(encoding='utf-8') for f in fp), fp


@case
def pr_links_command_sets_and_refuses():
    p = ENV.baseline()
    p.ok('pr-links', '--provider', 'gitlab', '--repo', 'acme-co/team/widgets', '--host', 'git.acme.example')
    assert p.man()['pr_links'] == GL
    bad = p.run('pr-links', '--provider', 'custom', '--template', 'https://x.example/changes')
    assert bad.code != 0, bad.all
    assert p.man()['pr_links'] == GL
    p.ok('render', '--all')
    assert p.man()['pr_links'] == GL, 'a set value is never replaced by the remote'


@case
def check_reports_a_bad_manifest_setting():
    p = ENV.baseline()
    path = p.rdir / 'manifest.json'
    m = json.loads(path.read_text(encoding='utf-8'))
    m['pr_links'] = {'provider': 'github', 'repo': 'nope'}
    path.write_text(json.dumps(m, indent=2) + '\n', encoding='utf-8')
    r = p.run('check')
    assert r.code != 0 and 'pr_links' in r.all, r.all


def main():
    global ENV
    T.TMP = Path(tempfile.mkdtemp(prefix='ptest272-'))
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
                print('FAIL', fn.__name__)
                traceback.print_exc()
    finally:
        T._rmtree(T.TMP)
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
