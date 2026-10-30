#!/usr/bin/env python3
"""Tests for claude/plugins/artifacts/scripts/render_artifacts.py (ARTIFACTSPEC 1.8.0, sections 4 to 6 and 14).

Every check of check_html gets a fixture that breaks exactly that rule and must produce exactly that
requirement ID; the clean fixtures must produce nothing. A check nobody has seen fire is not a check.

Run:  python -I tools/test_render_artifacts.py     (prints "N passed, 0 failed")
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'claude', 'plugins', 'artifacts')
sys.path.insert(0, os.path.join(PLUGIN, 'scripts'))

import render_artifacts as R  # noqa: E402

STAMP_TEXT, STAMP_ISO = '10 Oct 12:39', '2026-10-10T12:39+01:00'
FP_URL = 'https://claude.ai/artifact/fp-url'
AR_FILE, MP_FILE = 'feature-project-artifacts-standard.html', 'feature-model-and-effort-profiles.html'


# ------------------------------------------------------------------ fixture: the shape of the dev-standards record
def task(tid, owner, status, item, expected, changed='', app='', detail=None):
    return {'id': tid, 'owner': owner, 'app': app, 'status': status, 'item': item,
            'detail': detail if detail is not None else 'Detail of %s.' % item, 'expected': expected, 'changed': changed}


def base_registry():
    return {'spec': R.SPEC, 'updated': STAMP_ISO, 'tasks': [
        task('AR5', 'artifacts', 'Built', 'ARTIFACTSPEC 1.0.0', '10 Oct', '2026-10-10T11:00+01:00', 'luismc-artifacts'),
        task('AR6', 'artifacts', 'Running', 'Templates', '10 Oct ~15:30', '2026-10-10T12:00+01:00', 'luismc-artifacts'),
        task('AR7', 'artifacts', 'To do', 'project_artifacts.py', '11 Oct', '2026-10-09T09:00+01:00', 'luismc-artifacts'),
        task('AR16', 'artifacts', 'Built', 'Record saved', '20 Sep', '2026-09-20T10:00+01:00', 'luismc-artifacts'),
        task('DS1', 'project', 'Live', 'AUTHSPEC 3.1.0', '24 Sep', '2026-09-24T10:00+01:00', 'luismc-project-setup'),
        task('DS2', 'models', 'Live', 'Effort question', '05 Oct', '2026-10-05T10:00+01:00', 'luismc-project-setup'),
        task('DS3', 'project', 'Live', 'tech-stack-setup 11.2.0', '02 Oct', '2026-10-02T10:00+01:00', 'luismc-project-setup'),
        task('DS6', 'project', 'Running', 'Agent rules', '10 Oct ~13:45', '2026-10-10T10:00+01:00', 'luismc-project-setup'),
        task('DS7', 'project', 'Waiting', 'docs/ folder rule', '10 Oct ~13:45; CI', '2026-10-10T10:00+01:00', 'luismc-project-setup'),
        task('DS8', 'project', 'To do', 'Branch gates', '12 Oct', '2026-10-09T10:00+01:00', 'luismc-project-setup'),
        task('DS9', 'project', 'Needs you', 'Sign off the <rules> & ship', '11 Oct ~09:00; your review', '2026-10-10T09:00+01:00', 'luismc-project-setup'),
        task('DS10', 'project', 'On hold', 'Cloud routine', '30 Oct', '2026-10-01T10:00+01:00', 'luismc-project-setup'),
        task('DS11', 'project', 'Failed', 'Release CI', '10 Oct ~14:00', '2026-10-10T11:30+01:00', 'luismc-project-setup'),
        task('MP1', 'models', 'Live', 'Role rules', '08 Oct', '2026-10-08T10:00+01:00', 'luismc-project-setup'),
        task('MP2', 'models', 'Running', 'Skill profiles', '13 Oct', '2026-10-10T08:00+01:00', 'luismc-project-setup'),
    ]}


def base_manifest():
    return {
        'spec': R.SPEC, 'project': 'dev-standards', 'timezone': 'Europe/Lisbon', 'timezone_label': 'Lisbon',
        'windows_timezone': 'GMT Standard Time', 'design': 'default', 'default_branch': 'main', 'merged_status': 'Live',
        'full_progress_artifact': {'key': 'full-progress', 'title': 'Full Progress: dev-standards', 'url': FP_URL,
                                   'file': 'full-progress-dev-standards.html', 'published_sha256': ''},
        'feature_artifacts': [
            {'key': 'artifacts', 'title': 'Feature: Project artifacts standard',
             'file': AR_FILE, 'prefix': 'AR', 'apps': ['luismc-artifacts'], 'updated': '2026-10-10T12:39+01:00'},
            {'key': 'models', 'title': 'Feature: Model and effort profiles',
             'file': MP_FILE, 'prefix': 'MP', 'apps': ['luismc-project-setup'], 'updated': '2026-10-09T18:00+01:00'},
        ],
        'project_prefixes': ['DS'], 'updated': STAMP_ISO,
    }


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def make_content(record, key, lede, sections, history=None, extra_css='', hero='Hero with <code>code</code>.'):
    folder = os.path.join(record, 'content', key)
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': key, 'hero': hero, 'lede': lede, 'extra_css': extra_css}))
    for n, (slug, title, body) in enumerate(sections, 1):
        write(os.path.join(folder, '%02d-%s.html' % (n, slug)), '<!-- title: %s -->\n%s\n' % (title, body))
    if history is not None:
        write(os.path.join(folder, 'history.json'), json.dumps(history))


def make_record(root):
    """A record directory with content for the full-progress artifact and two feature artifacts."""
    record = os.path.join(root, 'docs', 'artifacts')
    make_content(record, 'full-progress', 'All ongoing work in dev-standards. More words follow.',
                 [('how-it-stays-current', 'How it stays current',
                   '<p>Status lives in the registry.</p>\n<ul><li>one</li></ul>')])
    make_content(record, 'artifacts', 'The design is agreed. The build runs today.',
                 [('what-and-why', 'What and why', '<h3>Why</h3>\n<p>Because.</p>'),
                  ('the-design', 'The design', '<div class="flow-steps"><div class="flow-step"><b>A</b></div></div>')],
                 history=[{'date': '10 Oct 12:39', 'change': 'Newest <change> & more.'},
                          {'date': '10 Oct 09:47', 'change': 'Older change.'},
                          {'date': '09 Oct 18:00', 'change': 'Oldest change.'}])
    make_content(record, 'models', 'Effort question is live! Rules ship next.',
                 [('what', 'What', '<p>Models.</p>')], history=[{'date': '10 Oct 10:00', 'change': 'Started.'}])
    return record


class Fixture:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='render-artifacts-')
        self.record = make_record(self.root)
        self.manifest = base_manifest()
        self.registry = base_registry()
        self.contents = self.reload()

    def reload(self):
        self.contents = {k: R.load_content(self.record, k) for k in ('full-progress', 'artifacts', 'models')}
        return self.contents

    def render(self, key, **kw):
        manifest = kw.get('manifest', self.manifest)
        registry = kw.get('registry', self.registry)
        return R.render_artifact(manifest, registry, kw.get('contents', self.contents), key, kw.get('plugin', PLUGIN),
                                 self.record, kw.get('stamp_text', STAMP_TEXT), kw.get('stamp_iso', STAMP_ISO),
                                 links=kw.get('links'))

    def check(self, html, key, **kw):
        return R.check_html(html, key, kw.get('manifest', self.manifest), kw.get('registry', self.registry),
                            kw.get('plugin', PLUGIN), self.record)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def sub1(html, old, new, count=1):
    assert html.count(old) == count, 'fixture error: %r found %d times, wanted %d' % (old, html.count(old), count)
    return html.replace(old, new)


def reqs(findings):
    return sorted({r for r, _ in findings})


def glance(html):
    """{group key: (task ids, decision ids, 'and N more' text, 'none' text)} of the At a glance block."""
    root = R.parse_dom(html)
    out = {}
    for g in R.find_all(root, 'details', 'glance-group'):
        more, none = R.find(g, 'li', 'glance-more'), R.find(g, 'p', 'glance-none')
        out[g.attrs['data-glance']] = (
            [li.attrs['data-glance-task'] for li in R.find_all(g, 'li', pred=lambda n: 'data-glance-task' in n.attrs)],
            [li.attrs['data-glance-decision'] for li in R.find_all(g, 'li', pred=lambda n: 'data-glance-decision' in n.attrs)],
            R.text_of(more) if more else '', R.text_of(none) if none else '')
    return out


def drop_item(html, attr, value):
    import re
    pattern = r'<li data-glance-%s="%s">.*?</li>\n?' % (attr, re.escape(value))
    assert len(re.findall(pattern, html)) == 1, (attr, value)
    return re.sub(pattern, '', html)


TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def with_fixture(fn):
    def wrapper():
        fx = Fixture()
        try:
            fn(fx)
        finally:
            fx.close()
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def expect(fx, html, key, want, **kw):
    got = fx.check(html, key, **kw)
    assert reqs(got) == sorted(want), 'wanted %s, got %s' % (sorted(want), got)
    return got


# ------------------------------------------------------------------ render: shape, determinism
@test
@with_fixture
def render_is_deterministic(fx):
    for key in ('full-progress', 'artifacts', 'models'):
        first = fx.render(key)
        again = fx.render(key, contents={k: R.load_content(fx.record, k) for k in ('full-progress', 'artifacts', 'models')})
        assert first == again and first.encode('utf-8') == again.encode('utf-8')


@test
@with_fixture
def full_progress_is_a_fragment_beginning_with_title(fx):
    """R5.29: the Artifact tool takes a fragment."""
    out = fx.render('full-progress')
    assert out.startswith('<title>'), out[:40]
    for tag in ('<!doctype', '<html', '<head>', '<body', '{{', '}}'):
        assert tag not in out, tag
    assert out.endswith('\n')


class _Collect(HTMLParser):
    """Reads a document the way a browser does, with no help from the renderer's own DOM."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.links, self.scripts, self.styles, self.ids, self.metas = [], [], [], [], set(), []
        self.stack, self.text, self.errors = [], {}, []

    def handle_decl(self, decl):
        self.tags.append(('decl', decl.lower()))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        self.stack.append(tag)
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'link':
            self.links.append(a)
        elif tag == 'meta':
            self.metas.append(a)
        elif tag in ('script', 'style'):
            (self.scripts if tag == 'script' else self.styles).append([a, ''])

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self.stack and self.stack[-1] in ('script', 'style'):
            (self.scripts if self.stack[-1] == 'script' else self.styles)[-1][1] += data
        if self.stack and self.stack[-1] == 'title':
            self.text['title'] = self.text.get('title', '') + data


def read_document(html):
    parser = _Collect()
    parser.feed(html)
    parser.close()
    return parser


@test
@with_fixture
def feature_artifact_is_a_standalone_document(fx):
    """R5.27: doctype, html lang, head (charset, viewport, title, fonts link, style) and body."""
    out = fx.render('artifacts')
    assert out.startswith('<!doctype html>\n<html lang="en">\n<head>\n'), out[:60]
    assert out.rstrip().endswith('</body>\n</html>')
    doc = read_document(out)
    names = [n for n, _ in doc.tags]
    assert names.index('html') < names.index('head') < names.index('title') < names.index('style') < names.index('body') < names.index('main')
    assert ('decl', 'doctype html') in doc.tags
    assert dict(doc.tags[names.index('html')][1]) == {'lang': 'en'}
    metas = doc.metas
    assert {'charset': 'utf-8'} in metas
    assert {'name': 'viewport', 'content': 'width=device-width, initial-scale=1'} in metas
    assert doc.text['title'] == 'Feature: Project artifacts standard'
    assert [s[0].get('id') for s in doc.styles] == ['design-tokens', 'structure-css', 'extra-css']
    assert '{{' not in out and '}}' not in out
    assert fx.check(out, 'artifacts') == []


@test
@with_fixture
def feature_artifact_needs_no_host(fx):
    """R5.28: opens by double-click: CSS inlined, nothing external but the fonts link, both themes' tokens present."""
    out = fx.render('artifacts')
    doc = read_document(out)
    css = {s[0]['id']: s[1] for s in doc.styles}
    assert css['structure-css'] == R.structure_css(PLUGIN)                 # project-artifact.css, inlined unchanged
    tokens = css['design-tokens']
    assert tokens == R.design_css(fx.manifest, PLUGIN, fx.record)
    assert R.check_tokens(tokens) == []
    assert ':root[data-theme="dark"]' in tokens and 'prefers-color-scheme: dark' in tokens   # light and dark
    hosts = sorted((l['rel'], l['href'].split('/')[2]) for l in doc.links)
    assert hosts == [('preconnect', 'fonts.googleapis.com'), ('preconnect', 'fonts.gstatic.com'),
                     ('stylesheet', 'fonts.googleapis.com')], hosts
    assert not any('src' in s[0] for s in doc.scripts)                      # one inline script, the template's own
    assert len(doc.scripts) == 1 and doc.scripts[0][1] == R._ui_script(PLUGIN, 'feature')
    for name, attrs in doc.tags:
        if isinstance(attrs, dict):
            assert not set(attrs) & {'src', 'srcset', 'poster', 'data'}, (name, attrs)
    assert 'href="project-artifact.css"' not in out and '@import' not in ''.join(css.values())
    # every contents link lands on a section of the same file
    hrefs = [a.attrs['href'] for a in R.find_all(R.find(R.parse_dom(out), 'nav'), 'a')]
    assert hrefs and all(h.startswith('#') and h[1:] in doc.ids for h in hrefs), hrefs
    # the same holds with a project design of its own
    write(os.path.join(fx.record, 'design.css'), R.design_css(fx.manifest, PLUGIN, fx.record).replace('Archivo', 'Rubik'))
    manifest = copy.deepcopy(fx.manifest)
    manifest['design'] = 'design.css'
    own = fx.render('artifacts', manifest=manifest)
    assert 'family=Rubik' in own and fx.check(own, 'artifacts', manifest=manifest) == []


@test
@with_fixture
def a_feature_artifact_without_fonts_needs_no_link_at_all(fx):
    plain = R.design_css(fx.manifest, PLUGIN, fx.record).replace('https://fonts.googleapis.com/css2?', 'https://example.test/css2?')
    write(os.path.join(fx.record, 'design.css'), plain)
    manifest = copy.deepcopy(fx.manifest)
    manifest['design'] = 'design.css'
    out = fx.render('artifacts', manifest=manifest)
    assert read_document(out).links == [] and fx.check(out, 'artifacts', manifest=manifest) == []


@test
@with_fixture
def render_has_no_crlf_difference(fx):
    plugin = os.path.join(fx.root, 'plugin-crlf')
    shutil.copytree(PLUGIN, plugin)
    for sub in ('templates', 'design'):
        for name in os.listdir(os.path.join(plugin, sub)):
            path = os.path.join(plugin, sub, name)
            if os.path.isfile(path):
                with open(path, 'rb') as handle:
                    data = handle.read().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                with open(path, 'wb') as handle:
                    handle.write(data)
    assert fx.render('full-progress', plugin=plugin) == fx.render('full-progress')
    assert fx.check(fx.render('full-progress'), 'full-progress', plugin=plugin) == []


@test
@with_fixture
def clean_fixtures_pass_every_check(fx):
    for key in ('full-progress', 'artifacts', 'models'):
        assert fx.check(fx.render(key), key) == [], (key, fx.check(fx.render(key), key))


@test
@with_fixture
def render_structure_and_look(fx):
    out = fx.render('artifacts')
    dom = R.parse_dom(out)
    assert R.text_of(R.find(dom, 'title')) == 'Feature: Project artifacts standard'
    nav = [R.text_of(a) for a in R.find_all(R.find(dom, 'nav'), 'a')]
    assert nav == ['0Status and checklist', '1What and why', '2The design', '3History'], nav
    assert 'Feature artifact &middot; dev-standards' in out
    assert 'fonts.googleapis.com/css2?family=Archivo' in out and 'rel="preconnect"' in out
    assert R.find(dom, 'style').attrs['id'] == 'design-tokens'
    assert 'data-theme="dark"' in out and 'id="theme-toggle"' in out
    time_node = R.find(dom, 'time')
    assert time_node.attrs['datetime'] == STAMP_ISO and R.text_of(R.find(dom, 'p', 'last-update')) == 'Last update: 10 Oct 12:39 (Lisbon)'
    assert R.find(dom, 'script', pred=lambda n: n.attrs.get('type') == 'application/json') is None  # feature: no registry
    th = [R.text_of(x) for x in R.find_all(R.find(dom, 'table', 'status-checklist'), 'th')]
    assert th == ['Status', 'Item', 'Detail', 'Expected (Lisbon)'], th


@test
@with_fixture
def full_progress_structure(fx):
    out = fx.render('full-progress')
    dom = R.parse_dom(out)
    nav = [R.text_of(a) for a in R.find_all(R.find(dom, 'nav'), 'a')]
    assert nav == ['0Status and checklist', '1Feature artifacts', '2How it stays current'], nav
    th = [R.text_of(x) for x in R.find_all(R.find(dom, 'table', 'status-checklist'), 'th')]
    assert th == ['Status', 'Item', 'App / service', 'Detail', 'Expected (Lisbon)'], th
    assert 'History' not in nav
    scripts = R.find_all(dom, 'script', pred=lambda n: n.attrs.get('type') == 'application/json')
    assert len(scripts) == 1 and scripts[0].attrs['id'] == 'task-registry'
    assert json.loads(''.join(c.text for c in scripts[0].children)) == fx.registry
    # R5.6: link, task ID range, first sentence of the lede
    s1node = R.find(dom, 'section', pred=lambda n: n.attrs.get('id') == 's1')
    cells = [[R.text_of(td) for td in R.find_all(tr, 'td')] for tr in R.find_all(s1node, 'tr', pred=lambda n: R.find(n, 'td'))]
    assert cells == [['Feature: Project artifacts standard', '10 Oct 12:39', 'AR5 to AR16', '1 Running2 Built1 To do', 'The design is agreed.'],
                     ['Feature: Model and effort profiles', '09 Oct 18:00', 'MP1 to MP2, DS2', '1 Running', 'Effort question is live!']], cells
    anchors = [a.attrs['href'] for a in R.find_all(s1node, 'a')]
    assert anchors == [AR_FILE, MP_FILE], anchors  # R5.30: every feature is linked to its file, relative


@test
@with_fixture
def render_escapes_text_from_the_registry(fx):
    out = fx.render('full-progress')
    body = out[:out.index('<script type="application/json"')] + out[out.index('</script>', out.index('<script type="application/json"')):]
    assert 'Sign off the &lt;rules&gt; &amp; ship' in body and '<rules>' not in body
    assert 'Newest &lt;change&gt; &amp; more.' in fx.render('artifacts')


@test
@with_fixture
def registry_in_script_cannot_break_out(fx):
    fx.registry['tasks'][0]['detail'] = 'a </script><b>x</b> <!-- y'
    out = fx.render('full-progress')
    dom = R.parse_dom(out)
    scripts = R.find_all(dom, 'script', pred=lambda n: n.attrs.get('type') == 'application/json')
    assert len(scripts) == 1
    assert json.loads(''.join(c.text for c in scripts[0].children)) == fx.registry
    assert fx.check(out, 'full-progress') == []


# ------------------------------------------------------------------ groups, order, Earlier fold, lede, tiles
def table_rows(html, which=0):
    """The groups and rows of the checklist in page order; which=0 the groups outside the Earlier fold, 1 the Earlier fold."""
    dom = R.parse_dom(html)
    out = []
    for node in R.elements(dom):
        in_earlier = R.has_ancestor(node, lambda n: n.tag == 'details' and R.has_class(n, 'earlier'))
        if in_earlier != bool(which):
            continue
        if node.tag == 'details' and R.has_class(node, 'status-fold') and not R.has_class(node, 'feature-group'):
            out.append(('group', node.attrs['data-group'], R.text_of(R.find(R.find(node, 'summary'), 'strong'))))
        elif node.tag == 'tr' and 'data-task' in node.attrs:
            out.append(('task', node.attrs['data-task']))
    return out


@test
@with_fixture
def groups_and_order_on_the_feature_artifact(fx):
    rows = table_rows(fx.render('artifacts'))
    assert rows == [('group', 'now', 'Running now and next'), ('task', 'AR6'), ('task', 'AR7'),
                    ('group', 'built', 'Live or built'), ('task', 'AR5'), ('task', 'AR16')], rows
    # the "you" group is omitted when empty; Live or built is newest changed first (AR5 11 Oct 10 > AR16 20 Sep)


@test
@with_fixture
def groups_and_order_on_the_full_progress_artifact(fx):
    rows = table_rows(fx.render('full-progress'))
    assert rows == [
        ('group', 'now', 'Not in a release yet'),
        ('task', 'DS6'), ('task', 'DS7'), ('task', 'AR6'),      # 10 Oct ~13:45 (twice, registry order), then 10 Oct ~15:30
        ('task', 'AR7'), ('task', 'DS8'), ('task', 'MP2'),      # 11 Oct, 12 Oct, 13 Oct
        ('group', 'you', 'Needs you, failed or on hold'),
        ('task', 'DS9'), ('task', 'DS11'), ('task', 'DS10'),    # Needs you, Failed, On hold
        ('group', 'built', 'Live or built'),
        ('task', 'AR5'), ('task', 'MP1'), ('task', 'DS2'), ('task', 'DS3'), ('task', 'AR16'),   # newest changed first; Built never folds
    ], rows


@test
@with_fixture
def earlier_fold_older_than_14_days(fx):
    out = fx.render('full-progress')
    assert table_rows(out, 1) == [('task', 'DS1')], table_rows(out, 1)   # only a Live row folds (24 Sep)
    dom = R.parse_dom(out)
    details = R.find_all(dom, 'details', 'earlier')
    assert len(details) == 1 and 'open' not in details[0].attrs and R.text_of(R.find(details[0], 'summary')) == 'Earlier'
    assert 'class="earlier"' not in fx.render('artifacts')  # a feature artifact never folds


@test
@with_fixture
def built_rows_never_fold(fx):
    """R6.3: unreleased work must not be hidden, however old."""
    for task_ in fx.registry['tasks']:
        if task_['id'] == 'AR16':
            task_['changed'] = '2025-01-01T10:00+00:00'                       # almost two years old, and Built
    out = fx.render('full-progress')
    assert ('task', 'AR16') in table_rows(out, 0) and ('task', 'AR16') not in table_rows(out, 1)
    assert fx.check(out, 'full-progress') == []
    # the same task released (Live) folds
    for task_ in fx.registry['tasks']:
        if task_['id'] == 'AR16':
            task_['status'] = 'Live'
    folded = fx.render('full-progress')
    assert ('task', 'AR16') in table_rows(folded, 1) and ('task', 'AR16') not in table_rows(folded, 0)
    # a registry with only old Built rows has no Earlier fold at all
    fx.registry['tasks'] = [dict(t_, status='Built', changed='2025-01-01T10:00+00:00') for t_ in fx.registry['tasks']
                            if t_['status'] in ('Live', 'Built')]
    assert 'class="earlier"' not in fx.render('full-progress')


@test
@with_fixture
def earlier_fold_boundary_is_14_days_from_the_stamp(fx):
    # stamp 10 Oct 12:39; a change at exactly 26 Sep 12:39 is 14 days old: not older, so it stays shown
    fx.registry['tasks'][4]['changed'] = '2026-09-26T12:39+01:00'          # DS1: exactly 14 days
    fx.registry['tasks'][6]['changed'] = '2026-09-26T12:38+01:00'          # DS3 (Live): one minute older
    out = fx.render('full-progress')
    assert table_rows(out, 1) == [('task', 'DS3')], table_rows(out, 1)
    assert ('task', 'DS1') in table_rows(out, 0)
    assert fx.check(out, 'full-progress') == []


@test
@with_fixture
def earlier_fold_follows_the_stamp_not_the_clock(fx):
    out = fx.render('full-progress', stamp_text='01 Oct 09:00', stamp_iso='2026-10-01T09:00+01:00')
    assert 'class="earlier"' not in out  # everything is within 14 days of 1 Oct except AR16 (11 days) - all shown
    assert ('task', 'AR16') in table_rows(out, 0)


@test
@with_fixture
def a_group_with_only_folded_rows_is_still_closed_correctly(fx):
    fx.registry['tasks'] = [t for t in fx.registry['tasks'] if t['status'] not in ('Live', 'Built') or t['id'] in ('AR16', 'DS1')]
    for task_ in fx.registry['tasks']:
        if task_['id'] == 'AR16':
            task_['status'] = 'Live'                                             # Built would stay shown
    out = fx.render('full-progress')
    rows = table_rows(out, 0)
    assert rows[-1] == ('group', 'built', 'Live or built'), rows               # the group holds only the Earlier fold
    assert table_rows(out, 1) == [('task', 'DS1'), ('task', 'AR16')]
    assert fx.check(out, 'full-progress') == []


@test
@with_fixture
def needs_you_sentence(fx):
    out = fx.render('full-progress')
    lede = R.text_of(R.find(R.parse_dom(out), 'p', 'lede'))
    assert lede == 'All ongoing work in dev-standards. More words follow.', lede     # R5.7: the note only
    assert glance(out)['you'][:2] == (['DS9', 'DS11'], []), glance(out)['you']
    # a feature artifact lists only its own tasks, and says so when there are none
    assert glance(fx.render('artifacts'))['you'] == ([], [], '', 'Nothing needs you.')
    fx.registry['tasks'][0]['status'] = 'Needs you'
    fx.registry['tasks'][0]['expected'] = '12 Oct'
    assert glance(fx.render('artifacts'))['you'][:2] == (['AR5'], [])
    # the sentence generator is still the reference for the set
    assert R.needs_you_sentence(fx.registry['tasks'][:1]) == 'Needs you: AR5 ARTIFACTSPEC 1.0.0.'


@test
def needs_you_sentence_unit():
    assert R.needs_you_sentence([]) == 'Nothing needs you.'
    got = R.needs_you_sentence([{'id': 'A1', 'status': 'Failed', 'item': 'x'}, {'id': 'A2', 'status': 'Needs you', 'item': 'y  z'},
                                {'id': 'A3', 'status': 'Running', 'item': 'q'}])
    assert got == 'Needs you: A2 y z; A1 x.', got


@test
@with_fixture
def tiles_count_each_status_in_order_and_skip_empty(fx):
    dom = R.parse_dom(fx.render('full-progress'))
    tiles = [(R.text_of(R.find(t, 'div', 'label')), R.text_of(R.find(t, 'div', 'count')), t.attrs['class'])
             for t in R.find_all(dom, 'div', 'status-count-tile')]
    assert tiles == [('tasks live', '4', 'status-count-tile status-live'), ('tasks built', '2', 'status-count-tile status-built'),
                     ('tasks running', '3', 'status-count-tile status-running'),
                     ('task needs you', '1', 'status-count-tile status-needs-you'), ('task waiting', '1', 'status-count-tile status-waiting'),
                     ('tasks to do', '2', 'status-count-tile status-to-do'), ('task on hold', '1', 'status-count-tile status-on-hold'),
                     ('task failed', '1', 'status-count-tile status-failed')], tiles
    feature = R.parse_dom(fx.render('artifacts'))
    got = [(R.text_of(R.find(t, 'div', 'label')), R.text_of(R.find(t, 'div', 'count'))) for t in R.find_all(feature, 'div', 'status-count-tile')]
    assert got == [('tasks built', '2'), ('task running', '1'), ('task to do', '1')], got


@test
@with_fixture
def full_progress_links_are_relative(fx):
    """R5.30: the committed file links to feature files by file name, so it works from a checkout."""
    out = fx.render('full-progress')
    dom = R.parse_dom(out)
    hrefs = {tr.attrs['data-task']: (R.find(tr, 'a').attrs['href'] if R.find(tr, 'a') else None)
             for tr in R.find_all(dom, 'tr', pred=lambda n: 'data-task' in n.attrs)}
    assert hrefs['AR6'] == AR_FILE and hrefs['AR5'] == AR_FILE and hrefs['AR16'] == AR_FILE
    assert hrefs['MP1'] == MP_FILE and hrefs['MP2'] == MP_FILE and hrefs['DS2'] == MP_FILE   # DS2 belongs to models
    assert hrefs['DS6'] is None                                                            # a project task has no link
    assert 'href="file:' not in out and 'data-copy="' not in out and 'class="local-path"' not in out and 'class="copy-link"' not in out
    for href in (h for h in hrefs.values() if h):
        assert '/' not in href and ':' not in href and href.endswith('.html')


@test
@with_fixture
def project_design_replaces_the_default(fx):
    default = R.design_css(fx.manifest, PLUGIN, fx.record)
    custom = default.replace('#2D46C8', '#0B7285').replace('Archivo', 'Rubik')
    write(os.path.join(fx.record, 'design.css'), custom)
    manifest = copy.deepcopy(fx.manifest)
    manifest['design'] = 'design.css'
    out = fx.render('artifacts', manifest=manifest)
    assert '#0B7285' in out and '#2D46C8' not in out and 'family=Rubik' in out
    assert fx.check(out, 'artifacts', manifest=manifest) == []
    # the same HTML does not satisfy a manifest that says "default"
    assert 'R5.10' in reqs(fx.check(out, 'artifacts'))


# ------------------------------------------------------------------ check_html: one fixture per check
@test
@with_fixture
def check_r51_title(fx):
    out = fx.render('artifacts')
    bad = sub1(out, 'Feature: Project artifacts standard', 'Project artifacts standard', count=2)
    expect(fx, bad, 'artifacts', ['R5.1'])
    bad = sub1(out, '<title>Feature: Project artifacts standard</title>', '<title>Feature: Something else</title>')
    expect(fx, bad, 'artifacts', ['R5.1'])
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, 'Full Progress: dev-standards', 'Progress: dev-standards', count=2), 'full-progress', ['R5.1'])


@test
@with_fixture
def check_r52_numbering_and_contents(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '&sect; 2</span>The design', '&sect; 3</span>The design'), 'artifacts', ['R5.2'])
    expect(fx, sub1(out, '<section id="s2">', '<section id="s5">'), 'artifacts', ['R5.2'])
    expect(fx, sub1(out, '<a href="#s2"><b>2</b>The design</a>', ''), 'artifacts', ['R5.2'])
    expect(fx, sub1(out, '<a href="#s2"><b>2</b>The design</a>', '<a href="#s2"><b>2</b>The plan</a>'), 'artifacts', ['R5.2'])


@test
@with_fixture
def check_r53_section_zero(fx):
    out = fx.render('artifacts')
    start = out.index('<p class="note">Key:')
    end = out.index('</p>', start) + 4
    expect(fx, out[:start] + out[end:], 'artifacts', ['R5.3'])                              # key missing
    stamp = out[out.index('<p class="last-update">'):out.index('</p>', out.index('<p class="last-update">')) + 4]
    moved = sub1(out, stamp + '\n', '')
    moved = sub1(moved, '</section>\n<section id="s1">', stamp + '\n</section>\n<section id="s1">')
    expect(fx, moved, 'artifacts', ['R5.3'])                                                 # stamp after the checklist
    bad = sub1(out, '<span class="status-chip status-live">Live</span> · ', '')
    expect(fx, bad, 'artifacts', ['R5.3'])                                                   # key lacks a status
    expect(fx, sub1(out, '</span>Status and checklist</h2>', '</span>Status</h2>'), 'artifacts', ['R5.2', 'R5.3'])


@test
@with_fixture
def check_r55_stamp(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, 'datetime="2026-10-10T12:39+01:00"', 'datetime="2026-10-10T12:39"'), 'artifacts', ['R5.5'])
    expect(fx, sub1(out, '>10 Oct 12:39</time>', '>10 Oct 12:40</time>'), 'artifacts', ['R5.5'])
    expect(fx, sub1(out, '12:39</time> (Lisbon)', '12:39</time> (Madeira)'), 'artifacts', ['R5.5'])
    expect(fx, sub1(out, 'Last update: <time', 'Updated: <time'), 'artifacts', ['R5.5'])
    expect(fx, sub1(out, '<time datetime="2026-10-10T12:39+01:00">10 Oct 12:39</time>', '10 Oct 12:39'), 'artifacts', ['R5.5'])


@test
@with_fixture
def check_r64_columns(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<th>Detail</th>', '', count=2), 'artifacts', ['R6.4'])
    expect(fx, sub1(out, 'Expected (Lisbon)', 'Expected', count=2), 'artifacts', ['R6.4'])
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, '<th>App / service</th>', '', count=4), 'full-progress', ['R6.4'])
    # a feature artifact must not carry the App / service column
    expect(fx, sub1(out, '<th>Detail</th>', '<th>App / service</th><th>Detail</th>', count=2), 'artifacts', ['R6.4'])


@test
@with_fixture
def check_r61_statuses(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<tr data-task="AR6"><td data-label="Status"><span class="status-chip status-running">', '<tr data-task="AR6"><td data-label="Status"><span class="status-chip status-live">'),
           'artifacts', ['R6.1'])
    got = fx.check(sub1(out, '<span class="status-chip status-running">Running</span></td><td data-label="Item"><span class="task-id">AR6',
                        '<span class="status-chip status-merged">Merged</span></td><td><span class="task-id">AR6'), 'artifacts')
    assert 'R6.1' in reqs(got), got


def uncollapse_replaced(h):
    """The first replaced decision as an always-open <article> instead of a closed <details>."""
    at = h.index('<details class="decision decision-replaced"')
    head, tail = h[:at], h[at:]
    tail = tail.replace('<details class="decision decision-replaced"', '<article class="decision decision-replaced"', 1)
    tail = tail.replace('<summary>', '<h3>', 1).replace('</summary>', '</h3>', 1).replace('</details>', '</article>', 1)
    return head + tail


def move_row(html, task_id, after_marker):
    start = html.index('<tr data-task="%s">' % task_id)
    end = html.index('</tr>', start) + 5
    row = html[start:end]
    html = html[:start] + html[end + 1:]
    at = html.index(after_marker)
    at = html.index('<tbody>', at) + len('<tbody>')
    return html[:at] + '\n' + row + html[at:]


@test
@with_fixture
def check_r62_groups(fx):
    fp = fx.render('full-progress')
    # a Running row placed under the "Needs you, failed or on hold" group
    expect(fx, move_row(fp, 'DS6', 'data-group="you"'), 'full-progress', ['R5.46'])
    # group heading text and order
    expect(fx, sub1(fp, '<strong>Not in a release yet</strong>', '<strong>Running next</strong>'), 'full-progress', ['R5.46'])
    # order inside a group: AR7 (11 Oct) moved before DS6 (10 Oct)
    expect(fx, move_row(fp, 'AR7', 'data-group="now"'), 'full-progress', ['R5.46'])
    # two groups swapped
    a, b = fp.index('<details class="status-fold" data-group="now"'), fp.index('<details class="status-fold" data-group="you"')
    c = fp.index('<details class="status-fold" data-group="built"')
    swapped = fp[:a] + fp[b:c] + fp[a:b] + fp[c:]
    expect(fx, swapped, 'full-progress', ['R5.46'])
    # Live or built not newest first
    out = fx.render('artifacts')
    expect(fx, move_row(out, 'AR16', 'data-group="built"'), 'artifacts', ['R6.2'])


@test
@with_fixture
def check_r63_earlier_fold(fx):
    fp = fx.render('full-progress')
    # un-fold: take the details out
    start = fp.index('<details class="earlier">')
    end = fp.index('</details>', start) + len('</details>')
    expect(fx, fp[:start] + fp[end:], 'full-progress', ['INV-1', 'R6.3'])            # rows lost entirely: also not in the checklist
    expect(fx, sub1(fp, '<details class="earlier">', '<details class="earlier" open>'), 'full-progress', ['R6.3'])
    expect(fx, sub1(fp, '<summary>Earlier</summary>', '<summary>Older</summary>'), 'full-progress', ['R6.3'])
    # a registry whose change dates disagree with the fold
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][5]['changed'] = '2026-08-01T10:00+01:00'                         # DS2 is old, but shown
    got = fx.check(sub1(fp, '<script type="application/json" id="task-registry">', '<script type="application/json" id="task-registry">'), 'full-progress', registry=registry)
    assert 'R6.3' in reqs(got), got
    # a Built row is never folded: AR16 (Built, 20 Sep) moved into Earlier by hand
    start = fp.index('<tr data-task="AR16">')
    end = fp.index('</tr>', start) + len('</tr>')
    row = fp[start:end]
    hidden = fp[:start] + fp[end:]
    at = hidden.index('</tbody>', hidden.index('<details class="earlier">'))
    hidden = hidden[:at] + row + '\n' + hidden[at:]
    assert 'R6.3' in reqs(fx.check(hidden, 'full-progress')), fx.check(hidden, 'full-progress')
    # a feature artifact has no fold
    feature = fx.render('artifacts')
    wrapped = sub1(feature, '</section>\n<section id="s1">', '<details class="earlier"><summary>Earlier</summary></details></section>\n<section id="s1">')
    assert 'R6.3' in reqs(fx.check(wrapped, 'artifacts'))


@test
@with_fixture
def check_r66_expected_format(fx):
    for bad in ('soon', 'today', 'tomorrow', 'next', '10 Oct ~25:00', '1 Oct', '10 October', '10 Oct ~15:30 sharp', '31 Feb', ''):
        registry = copy.deepcopy(fx.registry)
        registry['tasks'][1]['expected'] = bad                                         # AR6, Running
        out = fx.render('artifacts', registry=registry)
        got = fx.check(out, 'artifacts', registry=registry)
        assert reqs(got) == ['R6.6'], (bad, got)
    for good in ('10 Oct', '10 Oct ~15:30', '10 Oct; once CI is green', '10 Oct ~15:30; your CLAUDE.md ~15:55'):
        registry = copy.deepcopy(fx.registry)
        registry['tasks'][1]['expected'] = good
        assert fx.check(fx.render('artifacts', registry=registry), 'artifacts', registry=registry) == [], good
    # Live and Built rows are not held to the open-row format; Failed is not an open status
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][0]['expected'] = 'yesterday'
    registry['tasks'][12]['expected'] = 'soon'
    assert fx.check(fx.render('full-progress', registry=registry), 'full-progress', registry=registry) == []


@test
@with_fixture
def render_shows_the_expected_basis(fx):
    """R6.10, R6.11: a muted line under Expected on open rows of both kinds; never on Live or Built rows."""
    registry = copy.deepcopy(fx.registry)
    by_id = {t['id']: t for t in registry['tasks']}
    by_id['AR6']['expected_basis'] = 'agent slot ~01:30, ~1.5 h'            # Running
    by_id['DS9']['expected_basis'] = 'your review <& reply>'                  # Needs you
    by_id['DS1']['expected_basis'] = 'zzclosed'                               # Live: not shown
    for key, kind, wanted in (('artifacts', 'feature', ['AR6']), ('full-progress', 'full-progress', ['AR6', 'DS9'])):
        out = fx.render(key, registry=registry)
        assert out.count('class="expected-basis"') == len(wanted), (kind, out.count('class="expected-basis"'))
        assert '<span class="expected-basis">agent slot ~01:30, ~1.5 h</span></td>' in out, kind
        assert 'expected-basis">zzclosed' not in out, kind
        assert fx.check(out, key, registry=registry) == [], (kind, fx.check(out, key, registry=registry))
        if kind == 'full-progress':
            assert '<span class="expected-basis">your review &lt;&amp; reply&gt;</span></td>' in out
        # the Expected value itself is still the date, and the basis follows it
        assert '10 Oct ~15:30<span class="expected-basis">' in out, kind
    # no basis, no markup
    assert 'expected-basis' not in fx.render('artifacts').replace('.expected-basis', '')


@test
@with_fixture
def check_expected_basis_matches_registry(fx):
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][1]['expected_basis'] = 'CI run, ~20 min'                   # AR6, Running
    out = fx.render('artifacts', registry=registry)
    shown = '<span class="expected-basis">CI run, ~20 min</span>'
    expect(fx, sub1(out, shown, ''), 'artifacts', ['R6.10'], registry=registry)
    expect(fx, sub1(out, shown, shown.replace('20 min', '5 min')), 'artifacts', ['R6.10'], registry=registry)
    # a basis the registry does not have
    expect(fx, out, 'artifacts', ['R6.10'], registry=fx.registry)
    # a registry basis that is not a string is refused before rendering
    registry['tasks'][1]['expected_basis'] = 5
    try:
        fx.render('artifacts', registry=registry)
    except R.ContentError as e:
        assert 'expected_basis' in str(e)
    else:
        raise AssertionError('a non-string basis must be refused')


@test
def basis_style_uses_tokens_and_wraps():
    css = R.structure_css(PLUGIN)
    block = css[css.index('.expected-basis'):]
    block = block[:block.index('}')]
    assert 'display: block' in block and 'overflow-wrap: anywhere' in block and 'var(--ink-muted)' in block, block
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(', block), block      # tokens only


def checklist_folds(dom):
    """The R6.12 checklist groups: every status-fold except Full Progress's two feature folds (R5.50)."""
    return [f for f in R.find_all(dom, 'details', 'status-fold')
            if 'feature-group' not in f.attrs.get('class', '').split()]


@test
@with_fixture
def groups_are_collapsible_details(fx):
    """R6.12: every group is a native <details> with its heading in the <summary>, in both artifact kinds."""
    for kind, name in (('full-progress', 'full-progress'), ('artifacts', 'artifacts')):
        out = fx.render(name)
        dom = R.parse_dom(out)
        folds = checklist_folds(dom)
        assert folds and not R.find_all(dom, 'tr', 'status-group'), kind
        for fold in folds:
            kids = [n for n in fold.children if n.tag != '#text']
            assert kids[0].tag == 'summary' and R.find(kids[0], 'strong') is not None and R.find(fold, 'table', 'status-checklist')
        assert '<script' not in out[out.index('<details class="status-fold"'):out.index('</details>')]
        assert fx.check(out, name) == []
    fp = R.parse_dom(fx.render('full-progress'))
    built = [f for f in R.find_all(fp, 'details', 'status-fold') if f.attrs['data-group'] == 'built'][0]
    assert R.find(built, 'details', 'earlier') is not None           # the Earlier fold stays, inside Live or built


@test
@with_fixture
def live_or_built_starts_closed(fx):
    """R6.12: Live or built is always closed, every other group open; the closed heading still counts Built rows."""
    for name in ('full-progress', 'artifacts'):
        dom = R.parse_dom(fx.render(name))
        for fold in checklist_folds(dom):
            assert ('open' in fold.attrs) == (fold.attrs['data-group'] != 'built'), (name, fold.attrs)
    fp = R.parse_dom(fx.render('full-progress'))
    built = [f for f in R.find_all(fp, 'details', 'status-fold') if f.attrs['data-group'] == 'built'][0]
    assert R.text_of(R.find(built, 'span', 'fold-count')) == '2 built, 4 live', R.text_of(R.find(built, 'span', 'fold-count'))


@test
@with_fixture
def check_finds_a_wrong_open_state(fx):
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, 'data-group="built">', 'data-group="built" open>'), 'full-progress', ['R6.12'])
    expect(fx, sub1(fp, 'data-group="now" open>', 'data-group="now">'), 'full-progress', ['R6.12'])
    # a heading kept as a table row, and an Earlier fold moved out of Live or built
    row = '<tr data-task="DS6">'
    expect(fx, sub1(fp, row, '<tr class="status-group" data-group="now"><td colspan="5"><strong>x</strong></td></tr>' + row),
           'full-progress', ['R6.12'])


@test
@with_fixture
def glance_groups_are_collapsible_details(fx):
    """R6.13: each At a glance group is a <details> with the label and a task count in its <summary>; done groups start closed."""
    fx.registry = glance_registry()
    for name in ('full-progress', 'artifacts'):
        out = fx.render(name)
        dom = R.parse_dom(out)
        groups = R.find_all(dom, 'details', 'glance-group')
        assert groups and not R.find_all(dom, 'div', 'glance-group'), name
        for g in groups:
            kids = [n for n in g.children if n.tag != '#text']
            assert kids[0].tag == 'summary' and R.find(kids[0], 'span', 'glance-label') is not None
            assert ('open' in g.attrs) == (g.attrs['data-glance'] not in ('built', 'live')), (name, g.attrs)
        assert fx.check(out, name) == []
    out = fx.render('full-progress')
    counts = {g.attrs['data-glance']: R.text_of(R.find(g, 'span', 'fold-count'))
              for g in R.find_all(R.parse_dom(out), 'details', 'glance-group')}
    got = glance(out)
    for key, text in counts.items():
        n = len(got[key][0]) + len(got[key][1]) + (int(''.join(c for c in got[key][2] if c.isdigit())) if got[key][2] else 0)
        assert text == '%d task%s' % (n, '' if n == 1 else 's'), (key, text, n)
    empty = fx.render('artifacts')
    you = [g for g in R.find_all(R.parse_dom(empty), 'details', 'glance-group') if g.attrs['data-glance'] == 'you'][0]
    assert 'open' in you.attrs and R.text_of(R.find(you, 'p', 'glance-none')) == 'Nothing needs you.' or R.find(you, 'li')


@test
@with_fixture
def check_finds_a_wrong_glance_state(fx):
    fx.registry = glance_registry()
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, 'data-glance="live">', 'data-glance="live" open>'), 'full-progress', ['R6.13'])
    expect(fx, sub1(fp, 'data-glance="running" open>', 'data-glance="running">'), 'full-progress', ['R6.13'])
    at = fp.index('data-glance="you"')
    expect(fx, fp[:at] + fp[at:].replace('class="fold-count">', 'class="fold-count">9', 1), 'full-progress', ['R6.13'])


@test
def collapsible_group_style_is_accessible():
    css = R.structure_css(PLUGIN)
    block = css[css.index('details.status-fold > summary {'):]
    block = block[:block.index('}')]
    assert 'cursor: pointer' in block and 'min-height: 2.75rem' in block and 'list-style: none' in block, block
    assert not re.search(r'#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\(', block), block
    assert 'details.status-fold > summary:focus-visible' in css and 'details.status-fold[open] > summary::before' in css
    assert '@media print' in css and '::details-content' in css


@test
@with_fixture
def check_inv1_checklist_equals_registry(fx):
    out = fx.render('full-progress')
    for field, value in (('detail', 'Changed behind the registry.'), ('item', 'Other item'), ('app', 'other-app')):
        registry = copy.deepcopy(fx.registry)
        registry['tasks'][7][field] = value                                              # DS6
        expect(fx, out, 'full-progress', ['INV-1', 'R5.9'], registry=registry)           # the embedded registry also differs
    # status typed by hand into the HTML (the drift INV-1 exists to stop): chip, with the group and tile left alone
    feature = fx.render('artifacts')
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][2]['detail'] = 'Edited in the registry only.'                       # AR7
    expect(fx, feature, 'artifacts', ['INV-1'], registry=registry)
    # row removed
    start = feature.index('<tr data-task="AR7">')
    end = feature.index('</tr>', start) + 6
    expect(fx, feature[:start] + feature[end:], 'artifacts', ['INV-1'])
    # a row nobody registered, and a duplicate
    ghost = sub1(feature, '<tr data-task="AR7">', '<tr data-task="AR99"><td><span class="status-chip status-to-do">To do</span></td><td><span class="task-id">AR99</span>x</td><td>d</td><td>11 Oct</td></tr>\n<tr data-task="AR7">')
    assert 'INV-1' in reqs(fx.check(ghost, 'artifacts'))
    start = feature.index('<tr data-task="AR7">')
    end = feature.index('</tr>', start) + 6
    dup = feature[:end] + feature[start:end] + feature[end:]
    assert 'INV-1' in reqs(fx.check(dup, 'artifacts'))
    # a row without data-task
    assert 'INV-1' in reqs(fx.check(sub1(feature, '<tr data-task="AR7">', '<tr>'), 'artifacts'))


@test
@with_fixture
def check_inv1_other_artifacts_tasks_do_not_leak(fx):
    out = fx.render('artifacts')
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][9]['status'] = 'Failed'                                           # DS8 is a project task
    assert fx.check(out, 'artifacts', registry=registry) == []


@test
@with_fixture
def check_r58_tiles(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<div class="count">2</div><div class="label">tasks built</div>', '<div class="count">3</div><div class="label">tasks built</div>'),
           'artifacts', ['R5.8'])
    expect(fx, sub1(out, '<div class="status-count-tile status-running"><div class="count">1</div><div class="label">task running</div></div>', ''),
           'artifacts', ['R5.8'])
    expect(fx, sub1(out, '<div class="label">tasks built</div>', '<div class="label">tasks live</div>'), 'artifacts', ['R5.8'])
    expect(fx, sub1(out, '</div></div>\n<p class="note">Key', '</div><div class="status-count-tile status-failed"><div class="count">0</div><div class="label">tasks failed</div></div></div>\n<p class="note">Key'),
           'artifacts', ['R5.8'])


@test
@with_fixture
def check_r65_feature_tasks_linked_on_full_progress(fx):
    fp = fx.render('full-progress')
    linked = '<a href="%s"><span class="task-id">AR6</span>Templates</a>' % AR_FILE
    assert linked in fp
    expect(fx, sub1(fp, linked, '<span class="task-id">AR6</span>Templates'), 'full-progress', ['R6.5'])
    expect(fx, sub1(fp, linked, '<a href="feature-other.html"><span class="task-id">AR6</span>Templates</a>'), 'full-progress', ['R5.30'])
    # R5.30: the committed file never carries the publish copy's absolute links
    expect(fx, sub1(fp, linked, '<a href="file:///C:/x/docs/artifacts/%s"><span class="task-id">AR6</span>Templates</a>' % AR_FILE),
           'full-progress', ['R5.30'])
    # R5.31: the publish copy's rows carry no link, which the committed-file check reports as a missing link
    expect(fx, sub1(fp, linked, '<span class="task-id">AR6</span>Templates'), 'full-progress', ['R6.5'])
    expect(fx, sub1(fp, linked, '<a href="docs/artifacts/%s"><span class="task-id">AR6</span>Templates</a>' % AR_FILE),
           'full-progress', ['R5.30'])
    start = fp.index('<tr data-task="AR6">')
    end = fp.index('</tr>', start) + 6
    expect(fx, fp[:start] + fp[end:], 'full-progress', ['INV-1', 'R6.5'])


@test
@with_fixture
def check_r56_feature_list(fx):
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, '<a href="%s">Feature: Project artifacts standard</a>' % AR_FILE, 'Feature: Project artifacts standard'), 'full-progress', ['R5.6'])
    expect(fx, sub1(fp, '<a href="%s">Feature: Model and effort profiles</a>' % MP_FILE, '<a href="https://claude.ai/artifact/x">Feature: Model and effort profiles</a>'),
           'full-progress', ['R5.30'])
    expect(fx, sub1(fp, '<td data-label="Feature artifact" data-value="feature: model and effort profiles"><a href="%s">Feature: Model and effort profiles</a></td>' % MP_FILE, '<td>Feature: Model and effort</td>'), 'full-progress', ['R5.6'])


@test
@with_fixture
def check_r57_lede(fx):
    fp = fx.render('full-progress')
    expect(fx, drop_item(fp, 'task', 'DS11'), 'full-progress', ['R5.7'])                    # a Failed task missing
    out = fx.render('artifacts')
    wrong = sub1(out, '<p class="glance-none">Nothing needs you.</p>', '<ul><li data-glance-task="AR6"><span class="task-id">AR6</span>Templates</li></ul>')
    expect(fx, wrong, 'artifacts', ['R5.7'])                                                # a task that does not need you
    expect(fx, sub1(out, 'Nothing needs you.', 'All clear.'), 'artifacts', ['R5.7'])        # the exact text
    # a long or missing lede is not a finding
    assert fx.check(out, 'artifacts') == []


@test
@with_fixture
def check_r54_history(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<th>Change</th>', '<th>What</th>'), 'artifacts', ['R5.4'])
    # newest first
    bad = sub1(out, '<tr><td>10 Oct 12:39</td>', '<tr><td>08 Oct 12:39</td>')
    expect(fx, bad, 'artifacts', ['R5.4'])
    # History must be last: swap the titles of the last two sections (contents list kept in step)
    swapped = sub1(out, '</span>History</h2>', '</span>The end</h2>')
    swapped = sub1(swapped, '<b>3</b>History</a>', '<b>3</b>The end</a>')
    expect(fx, swapped, 'artifacts', ['R5.4'])
    fp = fx.render('full-progress')
    bad = sub1(fp, '</span>How it stays current</h2>', '</span>History</h2>')
    bad = sub1(bad, '<b>2</b>How it stays current</a>', '<b>2</b>History</a>')
    expect(fx, bad, 'full-progress', ['R5.4'])


@test
@with_fixture
def check_r59_registry_script(fx):
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, 'id="task-registry"', 'id="registry"'), 'full-progress', ['R5.9'])
    expect(fx, sub1(fp, '"status": "Running"', '"status": "Built"', count=fp.count('"status": "Running"')), 'full-progress', ['R5.9'])
    start = fp.index('<script type="application/json"')
    end = fp.index('</script>', start) + 9
    expect(fx, fp[:start] + fp[end:], 'full-progress', ['R5.9'])
    expect(fx, fp[:start] + '<script type="application/json" id="task-registry">{not json</script>' + fp[end:], 'full-progress', ['R5.9'])
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<div class="layout">', '<script type="application/json" id="task-registry">{}</script>\n<div class="layout">'),
           'artifacts', ['R5.9'])


@test
@with_fixture
def check_r410_no_script_or_style_in_content(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<p>Because.</p>', '<p>Because.</p><script>alert(1)</script>'), 'artifacts', ['R4.10'])
    expect(fx, sub1(out, '<p>Because.</p>', '<p>Because.</p><style>p{color:red}</style>'), 'artifacts', ['R4.10'])
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, '<p>Status lives in the registry.</p>', '<script>x()</script>'), 'full-progress', ['R4.10'])


@test
@with_fixture
def check_r510_structure_stylesheet_byte_identical(fx):
    out = fx.render('artifacts')
    css = R.structure_css(PLUGIN)
    expect(fx, sub1(out, '<style id="structure-css">' + css, '<style id="structure-css">' + css + 'a{color:red}'), 'artifacts', ['R5.10'])
    expect(fx, sub1(out, 'font-size: 16px;', 'font-size: 17px;'), 'artifacts', ['R5.10'])
    expect(fx, sub1(out, '<style id="structure-css">', '<style id="structure">'), 'artifacts', ['R4.10', 'R5.10'])
    # the token block must be the one the manifest names
    other = sub1(out, '--paper: #F5F6F8;', '--paper: #FAFAFA;')
    expect(fx, other, 'artifacts', ['R5.10'])


@test
@with_fixture
def check_r511_token_block_complete(fx):
    default = R.design_css(fx.manifest, PLUGIN, fx.record)
    manifest = copy.deepcopy(fx.manifest)
    manifest['design'] = 'design.css'
    out = fx.render('artifacts')
    for broken, label in (
        (default.replace('  --focus: #2D46C8;\n', '', 1), 'light value missing'),
        (default.replace('    --focus: #8EA2FF;\n', '', 1), 'dark media value missing'),
        (default.replace('  --failed: #F07167;\n', '', 1), 'dark attribute value missing'),
        (default.replace(':root[data-theme="dark"]', ':root[data-theme="night"]'), 'dark attribute block missing'),
        (default.replace('@media (prefers-color-scheme: dark)', '@media print'), 'dark media block missing'),
    ):
        write(os.path.join(fx.record, 'design.css'), broken)
        html = sub1(out, default, broken)
        got = fx.check(html, 'artifacts', manifest=manifest)
        assert reqs(got) == ['R5.11'], (label, got)
    assert R.check_tokens(default) == []
    # light value missing is reported for exactly that token
    write(os.path.join(fx.record, 'design.css'), default.replace('  --focus: #2D46C8;\n', '', 1))
    problems = R.check_tokens(R.design_css(manifest, PLUGIN, fx.record))
    assert problems == ['token --focus is not defined on :root'], problems


@test
@with_fixture
def project_design_missing_a_token_is_reported_and_refused(fx):
    default = R.design_css(fx.manifest, PLUGIN, fx.record)
    write(os.path.join(fx.record, 'design.css'), default.replace('  --on-failed: #FFFFFF;\n', ''))
    manifest = copy.deepcopy(fx.manifest)
    manifest['design'] = 'design.css'
    try:
        fx.render('full-progress', manifest=manifest)
    except R.ContentError as exc:
        assert any('--on-failed' in p for p in exc.problems), exc.problems
    else:
        raise AssertionError('a design without --on-failed rendered')
    try:
        R.design_css({'design': 'design.css'}, PLUGIN, os.path.join(fx.root, 'nowhere'))
    except R.ContentError as exc:
        assert 'design file not readable' in str(exc)
    else:
        raise AssertionError('a missing design.css was accepted')
    try:
        R.design_css({'design': 'fancy'}, PLUGIN, fx.record)
    except R.ContentError:
        pass
    else:
        raise AssertionError('an unknown design name was accepted')


@test
@with_fixture
def check_r411_extra_css_redefines_nothing(fx):
    out = fx.render('artifacts')
    for css in ('body { color: red; }', 'h2, .mine { margin: 0; }', 'nav.contents   a { x: y }', '@media (min-width: 1px) { .flow-step { x: y } }'):
        expect(fx, sub1(out, '<style id="extra-css"></style>', '<style id="extra-css">%s</style>' % css), 'artifacts', ['R4.11'])
    ok = sub1(out, '<style id="extra-css"></style>', '<style id="extra-css">.mine { color: var(--ink); }</style>')
    expect(fx, ok, 'artifacts', [])


@test
@with_fixture
def check_html_on_a_wrong_key_or_registry(fx):
    got = fx.check(fx.render('artifacts'), 'nope')
    assert reqs(got) == ['R4.2'], got
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][0]['status'] = 'Merged'
    got = fx.check(fx.render('artifacts'), 'artifacts', registry=registry)
    assert reqs(got) == ['R6.1'], got


# ------------------------------------------------------------------ load_content
def problems_of(fx, key='artifacts'):
    try:
        R.load_content(fx.record, key)
    except R.ContentError as exc:
        return exc.problems
    return []


@test
@with_fixture
def load_content_returns_the_documented_shape(fx):
    content = fx.contents['artifacts']
    assert set(content) == {'meta', 'sections', 'history', 'decisions'}
    assert set(content['meta']) == {'title', 'hero', 'lede', 'extra_css'}
    assert [s['title'] for s in content['sections']] == ['What and why', 'The design']
    assert content['sections'][0]['html'] == '<h3>Why</h3>\n<p>Because.</p>\n'
    assert content['history'][0] == {'date': '10 Oct 12:39', 'change': 'Newest <change> & more.'}
    assert fx.contents['full-progress']['history'] == []


@test
@with_fixture
def content_error_script_style_and_section_numbers(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts')
    for body, needle in (('<script>x()</script>', '<script>'), ('<style>p{}</style>', '<style>'),
                         ('<p>See § 3 below</p>', 'section number'), ('<h2><span class="section-number">3</span>x</h2>', 'section number'),
                         ('<div><p>open', 'not closed'), ('</div>', 'no opening tag')):
        write(os.path.join(folder, '02-the-design.html'), '<!-- title: The design -->\n%s\n' % body)
        found = problems_of(fx)
        assert any(needle in p and '02-the-design.html' in p for p in found), (body, found)


@test
@with_fixture
def content_error_titles(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts')
    for title in ('3. The design', '§ 3 The design', '3 - The design'):
        write(os.path.join(folder, '02-the-design.html'), '<!-- title: %s -->\n<p>x</p>\n' % title)
        assert any('starts with a section number' in p for p in problems_of(fx)), title
    write(os.path.join(folder, '02-the-design.html'), '<p>no title comment</p>\n')
    assert any('first line must be <!-- title:' in p for p in problems_of(fx))
    write(os.path.join(folder, '02-the-design.html'), '<!-- title: 2024 plans -->\n<p>x</p>\n')   # a year is not a section number
    assert problems_of(fx) == []


@test
@with_fixture
def content_error_numbering_and_names(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts')
    os.rename(os.path.join(folder, '02-the-design.html'), os.path.join(folder, '03-the-design.html'))
    assert any('without gaps' in p for p in problems_of(fx))
    os.rename(os.path.join(folder, '03-the-design.html'), os.path.join(folder, 'the-design.html'))
    found = problems_of(fx)
    assert any('NN-slug.html' in p for p in found), found
    os.rename(os.path.join(folder, 'the-design.html'), os.path.join(folder, '02-the-design.html'))
    write(os.path.join(folder, 'notes.txt'), 'x')
    assert any('not a content file' in p for p in problems_of(fx))


@test
@with_fixture
def content_error_meta(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts')
    write(os.path.join(folder, 'meta.json'), '{not json')
    assert any('meta.json' in p for p in problems_of(fx))
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'x', 'hero': '', 'lede': 5}))
    found = problems_of(fx)
    assert any('"hero"' in p for p in found) and any('"lede"' in p for p in found), found
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'x', 'hero': '<p>block</p>', 'lede': 'ok <script>x</script>'}))
    found = problems_of(fx)
    assert any('"hero" is inline text' in p for p in found) and any('"lede"' in p and 'script' in p for p in found), found
    os.remove(os.path.join(folder, 'meta.json'))
    assert any('meta.json' in p for p in problems_of(fx))
    try:
        R.load_content(fx.record, 'no-such-key')
    except R.ContentError as exc:
        assert 'does not exist' in str(exc)
    else:
        raise AssertionError('missing folder accepted')


@test
@with_fixture
def content_error_extra_css(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts')
    def meta(css):
        write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'x', 'hero': 'h', 'lede': 'l', 'extra_css': css}))
    meta('.flow-step { color: red; } body, .new { margin: 0 }')
    found = problems_of(fx)
    assert any('"body"' in p and 'R4.11' in p for p in found) and any('".flow-step"' in p for p in found), found
    assert not any('".new"' in p for p in found)
    meta('@media (max-width: 40rem) { nav.contents a { display: none } }')
    assert any('"nav.contents a"' in p for p in problems_of(fx))
    meta('.new-class { color: var(--ink); } .flow-step.big { x: y }')
    assert problems_of(fx) == []                      # adding classes, even refining a structure class, is allowed
    meta('</style><script>x()</script>')
    assert any('CSS only' in p for p in problems_of(fx))


@test
@with_fixture
def content_error_history(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts')
    write(os.path.join(folder, 'history.json'), json.dumps([{'date': '10 Oct'}, 'x']))
    found = problems_of(fx)
    assert len([p for p in found if 'history.json' in p]) == 2, found
    write(os.path.join(folder, 'history.json'), '{"a": 1}')
    assert any('must hold a list' in p for p in problems_of(fx))
    write(os.path.join(fx.record, 'content', 'full-progress', 'history.json'), '[]')
    assert any('no History' in p for p in problems_of(fx, 'full-progress'))


@test
@with_fixture
def content_error_lists_every_problem(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts')
    write(os.path.join(folder, '01-what-and-why.html'), '<!-- title: 1. What -->\n<script>a</script><style>b</style>\n')
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'x', 'hero': '', 'lede': 'l', 'extra_css': 'body{}'}))
    found = problems_of(fx)
    assert len(found) >= 5, found
    try:
        R.load_content(fx.record, 'artifacts')
    except R.ContentError as exc:
        assert exc.problems == found and isinstance(exc, Exception)
        assert str(exc) == '; '.join(found)


# ------------------------------------------------------------------ render_artifact refuses what it cannot render
@test
@with_fixture
def render_errors(fx):
    def fails(needle, **kw):
        try:
            fx.render(kw.pop('key', 'artifacts'), **kw)
        except R.ContentError as exc:
            assert any(needle in p for p in exc.problems), exc.problems
        else:
            raise AssertionError('rendered despite: ' + needle)
    fails('not in the manifest', key='nope')
    fails('stamp_text', stamp_text='Last update: 10 Oct 12:39')
    fails('does not match stamp_iso', stamp_text='10 Oct 12:40')
    fails('ISO time with an offset', stamp_iso='2026-10-10T12:39')
    fails('ISO time with an offset', stamp_iso='nonsense')
    manifest = copy.deepcopy(fx.manifest)
    manifest['feature_artifacts'][0]['title'] = 'Project artifacts standard'
    fails('must start with "Feature: "', manifest=manifest)
    manifest = copy.deepcopy(fx.manifest)
    del manifest['timezone_label']
    fails('timezone_label', manifest=manifest)
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][0]['status'] = 'Merged'
    fails("status 'Merged'", registry=registry)
    fails('no content loaded', contents={})
    contents = dict(fx.contents)
    del contents['models']
    fails('no content loaded for feature artifact', key='full-progress', contents=contents)


@test
@with_fixture
def stamp_may_be_in_any_offset(fx):
    out = fx.render('artifacts', stamp_text='10 Oct 23:05', stamp_iso='2026-10-10T23:05-07:00')
    assert 'datetime="2026-10-10T23:05-07:00"' in out and fx.check(out, 'artifacts') == []
    assert R.text_of(R.find(R.parse_dom(out), 'p', 'last-update')) == 'Last update: 10 Oct 23:05 (Lisbon)'


# ------------------------------------------------------------------ artifact_file, constants
@test
def artifact_file_names():
    assert R.artifact_file('feature', 'Feature: Project artifacts standard') == 'feature-project-artifacts-standard.html'
    assert R.artifact_file('full-progress', 'Full Progress: dev-standards') == 'full-progress-dev-standards.html'
    assert R.artifact_file('feature', 'Model and effort profiles') == 'feature-model-and-effort-profiles.html'
    assert R.artifact_file('feature', 'Feature: Sign-in & SSO (v2)!') == 'feature-sign-in-sso-v2.html'
    assert R.artifact_file('feature', 'Feature: Café Menü') == 'feature-cafe-menu.html'
    for args in (('page', 'x'), ('feature', 'Feature: !!!'), ('feature', '')):
        try:
            R.artifact_file(*args)
        except ValueError:
            pass
        else:
            raise AssertionError(args)


@test
def constants_follow_the_contract():
    assert R.STATUSES == ('Live', 'Built', 'Running', 'Needs you', 'Waiting', 'To do', 'On hold', 'Failed', 'Dropped')
    assert len(R.REQUIRED_TOKENS) == 22 and len(set(R.REQUIRED_TOKENS)) == 22
    design = open(os.path.join(PLUGIN, 'design', 'DESIGN.md'), encoding='utf-8').read()
    for token in R.REQUIRED_TOKENS:
        assert '`%s`' % token in design, token
    for token in R.STATUSES:
        assert R.status_class(token) == 'status-' + token.lower().replace(' ', '-')
    css = R.structure_css(PLUGIN)
    for status in R.STATUSES:
        assert '.status-chip.%s' % R.status_class(status) in css, status          # R6.1: each chip class is styled
        assert '.status-count-tile.%s' % R.status_class(status) in css, status


@test
def the_default_design_is_a_complete_token_block():
    css = R.design_css({'design': 'default'}, PLUGIN, '')
    assert R.check_tokens(css) == []
    assert R.check_tokens('') and len(R.check_tokens('')) == 22 + 2 * len(R.DARK_TOKENS)


@test
def the_structure_stylesheet_holds_no_literal_colour():
    import re
    css = re.sub(r'/\*.*?\*/', '', R.structure_css(PLUGIN), flags=re.S)
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(', css)


@test
@with_fixture
def templates_hold_only_known_placeholders(fx):
    import re
    known = {'title', 'fonts_link', 'design_css', 'structure_css', 'extra_css', 'kind_label', 'project', 'hero', 'contents', 'glance',
             'sections', 'stamp', 'published', 'lede', 'tiles', 'key', 'timeline', 'checklist', 'registry'}
    for name in ('feature-artifact.html', 'full-progress-artifact.html'):
        text = open(os.path.join(PLUGIN, 'templates', name), encoding='utf-8').read()
        found = set(re.findall(r'\{\{(\w+)\}\}', text))
        assert found <= known, found - known
        if name.startswith('feature'):
            assert text.startswith('<!doctype html>\n<html lang="en">'), text[:40]   # a complete document (R5.27)
            assert text.rstrip().endswith('</body>\n</html>')
        else:
            assert text.startswith('<title>{{title}}</title>')                      # a fragment (R5.29)
        assert ('{{registry}}' in text) == (name.startswith('full-progress'))
        assert text.count('<script') == 1 or (name.startswith('full') and text.count('<script') == 1)


# ------------------------------------------------------------------ standalone files and links (section 5.5)
@test
@with_fixture
def check_r527_standalone_document(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<!doctype html>\n', ''), 'artifacts', ['R5.27'])
    expect(fx, sub1(out, '<!doctype html>', '<!DOCTYPE HTML>'), 'artifacts', [])                 # case does not matter
    expect(fx, sub1(out, '<html lang="en">', '<html>'), 'artifacts', ['R5.27'])
    expect(fx, sub1(out, '<html lang="en">', '<html lang="">'), 'artifacts', ['R5.27'])
    expect(fx, sub1(out, '<meta charset="utf-8">\n', ''), 'artifacts', ['R5.27'])
    expect(fx, sub1(out, '<meta name="viewport" content="width=device-width, initial-scale=1">\n', ''), 'artifacts', ['R5.27'])
    # the old claude.ai form: a fragment beginning with <title>
    old_form = out[out.index('<title>'):out.index('</head>')] + out[out.index('</head>\n<body>\n') + len('</head>\n<body>\n'):out.index('</body>')]
    got = fx.check(old_form, 'artifacts')
    assert 'R5.27' in reqs(got), got
    # the page outside the body
    expect(fx, sub1(sub1(out, '</head>\n<body>\n', '</head>\n'), '</body>\n', ''), 'artifacts', ['R5.27'])


@test
@with_fixture
def check_r528_no_external_resources(fx):
    out = fx.render('artifacts')
    link = '<link rel="stylesheet" href="project-artifact.css">\n'
    expect(fx, sub1(out, '<style id="design-tokens">', link + '<style id="design-tokens">'), 'artifacts', ['R5.28'])
    other = '<link rel="stylesheet" href="https://cdn.example.test/a.css">\n'
    expect(fx, sub1(out, '<style id="design-tokens">', other + '<style id="design-tokens">'), 'artifacts', ['R5.28'])
    pre = '<link rel="preconnect" href="https://cdn.example.test">\n'
    expect(fx, sub1(out, '<style id="design-tokens">', pre + '<style id="design-tokens">'), 'artifacts', ['R5.28'])
    fonts_only = '<link rel="icon" href="https://fonts.gstatic.com/x.ico">\n'
    expect(fx, sub1(out, '<style id="design-tokens">', fonts_only + '<style id="design-tokens">'), 'artifacts', ['R5.28'])
    expect(fx, sub1(out, '<div class="layout">', '<script src="app.js"></script>\n<div class="layout">'), 'artifacts', ['R4.10', 'R5.28'])
    expect(fx, sub1(out, '<p>Because.</p>', '<p>Because.</p><img src="logo.png" alt="">'), 'artifacts', ['R5.28'])
    expect(fx, sub1(out, '<p>Because.</p>', '<p>Because.</p><img src="data:image/png;base64,AAAA" alt="">'), 'artifacts', [])
    expect(fx, sub1(out, '<style id="extra-css"></style>', '<style id="extra-css">@import url(https://cdn.example.test/a.css);</style>'),
           'artifacts', ['R5.28'])
    expect(fx, sub1(out, '<style id="extra-css"></style>', '<style id="extra-css">.x{background:url(https://cdn.example.test/a.png)}</style>'),
           'artifacts', ['R5.28'])
    expect(fx, sub1(out, '<style id="extra-css"></style>', '<style id="extra-css">.x{background:url(data:image/png;base64,AAAA)}</style>'),
           'artifacts', [])


@test
@with_fixture
def check_r529_full_progress_fragment(fx):
    fp = fx.render('full-progress')
    document = '<!doctype html>\n<html lang="en">\n<head>\n' + fp + '</head>\n<body></body>\n</html>\n'
    assert 'R5.29' in reqs(fx.check(document, 'full-progress')), fx.check(document, 'full-progress')
    assert 'R5.29' in reqs(fx.check('<!-- x -->\n' + fp, 'full-progress'))
    assert 'R5.29' in reqs(fx.check('<body>' + fp + '</body>', 'full-progress'))
    assert fx.check(fp, 'full-progress') == []


@test
@with_fixture
def check_r530_relative_links(fx):
    """R5.30: the committed full-progress file links by file name; the publish copy's links fail the check."""
    fp = fx.render('full-progress')
    assert fx.check(fp, 'full-progress') == []
    copy_ = fx.render('full-progress', links=publish_links(fx))
    got = fx.check(copy_, 'full-progress')
    assert 'R6.5' in reqs(got) and 'R5.6' in reqs(got), got              # the copy has no relative links: it is not what is committed
    # section 1 and a task link, each broken alone
    expect(fx, sub1(fp, '<a href="%s">Feature: Project artifacts standard</a>' % AR_FILE,
                    '<a href="./%s">Feature: Project artifacts standard</a>' % AR_FILE), 'full-progress', ['R5.30'])
    expect(fx, sub1(fp, '<a href="%s"><span class="task-id">MP2</span>' % MP_FILE,
                    '<a href="../%s"><span class="task-id">MP2</span>' % MP_FILE), 'full-progress', ['R5.30'])
    # a feature artifact has no such links to check
    assert fx.check(fx.render('artifacts'), 'artifacts') == []


def publish_links(fx, root='/home/me/my repo'):
    """What project_artifacts.py hands render_artifact for the publish copy (R5.31)."""
    out = {}
    for entry in fx.manifest['feature_artifacts']:
        path = '%s/docs/artifacts/%s' % (root, entry['file'])
        out[entry['key']] = ('file://' + path.replace(' ', '%20'), path)
    return out


@test
@with_fixture
def publish_copy_has_file_links(fx):
    """R5.31: the copy names each feature as text with one Copy link button holding its file:/// address."""
    links = publish_links(fx)
    copy_ = fx.render('full-progress', links=links)
    committed = fx.render('full-progress')
    assert copy_ != committed
    dom = R.parse_dom(copy_)
    assert 'href="file:' not in copy_ and 'href="feature-' not in copy_                 # a page on claude.ai cannot open them
    assert not [a for a in R.find_all(dom, 'a') if a.attrs['href'].startswith(('file:', 'feature-'))]
    buttons = R.find_all(dom, 'button', 'copy-link')
    assert sorted(b.attrs['data-copy'] for b in buttons) == sorted(v[0] for v in links.values()), len(buttons)
    assert len(buttons) == len(links) == len(fx.manifest['feature_artifacts'])           # exactly one per feature
    assert 'file:///home/me/my%20repo/docs/artifacts/' + AR_FILE in copy_
    # the buttons are in section 1 only; the checklist rows carry no link at all
    table = R.find(dom, 'table', 'status-checklist')
    assert not R.find_all(table, 'button', 'copy-link') and not R.find_all(table, 'a')
    assert not R.find_all(table, 'code', 'local-path')
    feature_list = R.find(dom, 'table', 'feature-list')
    assert len(R.find_all(feature_list, 'button', 'copy-link')) == len(buttons)
    for button in buttons:
        assert R.text_of(button) == 'Copy link'
        siblings = [n for n in button.parent.children if n.tag != '#text' or n.text.strip()]
        before, after = siblings[siblings.index(button) - 1], siblings[siblings.index(button) + 1]
        assert before.tag == 'span' and R.has_class(before, 'feature-name')              # the name, as text
        assert after.tag == 'code' and R.has_class(after, 'local-path') and 'hidden' in after.attrs
        assert R.text_of(after) == button.attrs['data-copy']                             # shown only if the clipboard refuses
        assert button.attrs['title'].startswith('/home/me/my repo/docs/artifacts/')       # the path, as the tooltip
    # the stamp, the registry script and the rows are those of the committed file
    assert R.text_of(R.find(dom, 'p', 'last-update')) == 'Last update: 10 Oct 12:39 (Lisbon)'
    assert json.loads(''.join(c.text for c in R.find(dom, 'script', pred=lambda n: n.attrs.get('type') == 'application/json').children)) == fx.registry
    assert len(R.find_all(R.find(R.parse_dom(committed), 'table', 'status-checklist'), 'tr')) == len(R.find_all(table, 'tr'))


@test
@with_fixture
def publish_copy_path_encoding(fx):
    """R5.31: the address is as given (percent-encoded by the caller), the path text is escaped, not encoded."""
    links = {'artifacts': ('file:///C:/My%20Docs/a%26b/docs/artifacts/' + AR_FILE, 'C:/My Docs/a&b/docs/artifacts/' + AR_FILE),
             'models': ('file:///C:/My%20Docs/a%26b/docs/artifacts/' + MP_FILE, 'C:/My Docs/a&b/docs/artifacts/' + MP_FILE)}
    out = fx.render('full-progress', links=links)
    assert 'data-copy="file:///C:/My%20Docs/a%26b/docs/artifacts/' + AR_FILE + '"' in out
    assert 'title="C:/My Docs/a&amp;b/docs/artifacts/' + AR_FILE + '"' in out
    assert '<code class="local-path" hidden>file:///C:/My%20Docs/a%26b/docs/artifacts/' + AR_FILE + '</code>' in out
    assert 'href="file:' not in out
    assert '&amp;amp;' not in out and 'a&b' not in out.replace('a&amp;b', '')
    # a feature artifact has no links to feature files, whatever it is given
    assert fx.render('artifacts', links=links) == fx.render('artifacts')


@test
@with_fixture
def publish_copy_with_partial_links_keeps_relative_for_the_rest(fx):
    out = fx.render('full-progress', links={'artifacts': ('file:///x/' + AR_FILE, '/x/' + AR_FILE)})
    assert out.count('class="copy-link"') == 1 and 'data-copy="file:///x/%s"' % AR_FILE in out
    assert 'href="%s"' % MP_FILE in out and 'href="%s"' % AR_FILE not in out            # the rest stay relative links


# ------------------------------------------------------------------ decisions (section 5.4)
PNG =b'\x89PNG\r\n\x1a\n' + b'not-a-real-image-the-renderer-only-embeds-bytes'


def opt(label, summary=None, **kw):
    out = {'label': label, 'summary': '%s, in a sentence.' % label if summary is None else summary}
    out.update(kw)
    return out


def dec(n, **kw):
    """A decided decision D<n> by default; keyword arguments replace its fields."""
    out = {'id': 'D%d' % n, 'question': 'Which layout for the checkout page?', 'asked': '2026-10-08', 'status': 'decided',
           'options': [opt('Single page', recommended=True, preview='<pre>+------+\n| Pay  |\n+------+</pre>'),
                       opt('Three steps')],
           'chosen': 'Single page', 'decided': '2026-10-10', 'owner_words': 'single page, fewer clicks', 'task': 'AR6'}
    out.update(kw)
    return out


def open_dec(n, **kw):
    out = dec(n, question='Should History also list decisions?', status='open', chosen=None, decided=None, owner_words=None,
              options=[opt('Yes'), opt('No', recommended=True)], task='AR7')
    out.update(kw)
    return out


def put_decisions(fx, decisions, key='artifacts', raw=None):
    path = os.path.join(fx.record, 'content', key, 'decisions.json')
    write(path, raw if raw is not None else json.dumps({'decisions': decisions}, indent=1))
    return path


def load_problems(fx, key='artifacts'):
    try:
        R.load_content(fx.record, key)
    except R.ContentError as exc:
        return exc.problems
    return []


def three_decisions():
    """D1 decided and later replaced, D2 open, D3 decided (replaces D1)."""
    return [dec(1), open_dec(2), dec(3, question='Which layout, second thoughts?', asked='2026-10-10', replaces='D1',
                                    options=[opt('Single page'), opt('Wizard', recommended=True)], chosen='Wizard',
                                    owner_words='wizard, it is clearer', task=None)]


def sample(fx, decisions=None):
    put_decisions(fx, three_decisions() if decisions is None else decisions)
    fx.reload()
    registry = copy.deepcopy(fx.registry)
    for t in registry['tasks']:
        if t['id'] == 'AR7':
            t.update(status='Needs you', expected='11 Oct')
    return registry


@test
@with_fixture
def decisions_valid_file_loads_normalised(fx):
    put_decisions(fx, [dec(1), open_dec(2)])
    content = R.load_content(fx.record, 'artifacts')
    d1, d2 = content['decisions']
    assert d1['id'] == 'D1' and d1['chosen'] == 'Single page' and d1['options'][0]['recommended'] is True
    assert d1['options'][1]['recommended'] is False and d1['options'][1]['preview'] == '' and d1['options'][1]['image_uri'] == ''
    assert d2['status'] == 'open' and d2['chosen'] is None and d2['decided'] is None and d2['replaces'] is None
    assert R.load_content(fx.record, 'models')['decisions'] == []          # no file, no decisions


@test
@with_fixture
def decisions_yes_no_question_lists_both(fx):
    put_decisions(fx, [open_dec(1)])
    assert load_problems(fx) == []


SCHEMA_CASES = [
    # (name, decision list builder, text the problem must hold, requirement)
    ('one option only', lambda: [dec(1, options=[opt('Single page')])], '2 to 6 options', 'R5.16'),
    ('seven options', lambda: [dec(1, options=[opt('O%d' % i) for i in range(7)], chosen='O1')], '2 to 6 options', 'R5.16'),
    ('options not a list', lambda: [dec(1, options='Yes or no')], '2 to 6 options', 'R5.16'),
    ('duplicate labels', lambda: [dec(1, options=[opt('Single page'), opt('Single page')])], 'used twice', 'R5.16'),
    ('duplicate labels differing in case', lambda: [dec(1, options=[opt('Single page'), opt('single PAGE ')])], 'used twice', 'R5.16'),
    ('empty label', lambda: [dec(1, options=[opt(''), opt('B')], chosen='B')], '"label"', 'R5.16'),
    ('empty summary', lambda: [dec(1, options=[opt('Single page', summary=''), opt('B')])], '"summary"', 'R5.14'),
    ('decided without chosen', lambda: [dec(1, chosen=None)], 'label of one of its options', 'R5.16'),
    ('chosen is not a label', lambda: [dec(1, chosen='Four steps')], 'label of one of its options', 'R5.16'),
    ('decided without a date', lambda: [dec(1, decided=None)], '"decided" must be a date', 'R5.16'),
    ('decided before asked', lambda: [dec(1, decided='2026-10-01')], 'before "asked"', 'R5.16'),
    ('open with a choice', lambda: [open_dec(1, chosen='Yes')], 'must be null', 'R5.16'),
    ('open with a decided date', lambda: [open_dec(1, decided='2026-10-10')], 'must be null', 'R5.16'),
    ('open with the owner\'s words', lambda: [open_dec(1, owner_words='yes please')], 'no "owner_words"', 'R5.16'),
    ('status outside decided or open', lambda: [dec(1, status='closed')], '"status"', 'R5.16'),
    ('two recommended', lambda: [dec(1, options=[opt('A', recommended=True), opt('B', recommended=True)], chosen='A')],
     'at most one', 'R5.16'),
    ('recommended not a boolean', lambda: [dec(1, options=[opt('A', recommended='yes'), opt('B')], chosen='B')],
     '"recommended"', 'R5.16'),
    ('replaces an unknown decision', lambda: [dec(1), dec(2, replaces='D9')], 'earlier decision', 'R5.18'),
    ('replaces a later decision', lambda: [dec(1, replaces='D2'), dec(2)], 'earlier decision', 'R5.18'),
    ('replaces itself', lambda: [dec(1, replaces='D1')], 'earlier decision', 'R5.18'),
    ('task is not an ID', lambda: [dec(1, task='the checkout')], '"task"', 'R5.18'),
    ('id gap (a decision was removed)', lambda: [dec(1), dec(3)], 'no gap', 'R5.15'),
    ('id reused', lambda: [dec(1), dec(1)], 'no gap', 'R5.15'),
    ('id malformed', lambda: [dec(1, id='d1')], 'D1, D2', 'R5.15'),
    ('unknown decision field', lambda: [dec(1, chosn='x')], 'unknown field', 'R5.14'),
    ('unknown option field', lambda: [dec(1, options=[opt('A', colour='red'), opt('B')], chosen='B')], 'unknown field', 'R5.14'),
    ('question missing', lambda: [dec(1, question='')], '"question"', 'R5.14'),
    ('question too long', lambda: [dec(1, question='Q' * 201)], '"question"', 'R5.14'),
    ('asked is not a real date', lambda: [dec(1, asked='2026-02-30')], '"asked"', 'R5.14'),
    ('asked in the wrong format', lambda: [dec(1, asked='10 Oct')], '"asked"', 'R5.14'),
    ('a decision that is not an object', lambda: [dec(1), 'D2'], 'not an object', 'R5.14'),
    ('preview and image together', lambda: [dec(1, options=[opt('A', preview='<p>x</p>', image='assets/a.png'), opt('B')], chosen='B')],
     'not both', 'R5.17'),
    ('image that does not exist', lambda: [dec(1, options=[opt('A', image='assets/none.png'), opt('B')], chosen='B')],
     'does not exist', 'R5.17'),
    ('image outside the content folder', lambda: [dec(1, options=[opt('A', image='../meta.json'), opt('B')], chosen='B')],
     'assets/<file name>', 'R5.17'),
    ('image in a subfolder', lambda: [dec(1, options=[opt('A', image='assets/x/a.png'), opt('B')], chosen='B')],
     'assets/<file name>', 'R5.17'),
    ('image of the wrong type', lambda: [dec(1, options=[opt('A', image='assets/a.svg'), opt('B')], chosen='B')],
     'png, jpg, gif or webp', 'R5.17'),
]


@test
@with_fixture
def decisions_schema_every_rule_fails_alone(fx):
    for name, build, needle, req in SCHEMA_CASES:
        write(os.path.join(fx.record, 'content', 'artifacts', 'assets', 'a.svg'), '<svg xmlns="http://www.w3.org/2000/svg"/>')
        put_decisions(fx, build())
        problems = load_problems(fx)
        hits = [p for p in problems if needle in p]
        assert hits, '%s: no problem holds %r in %s' % (name, needle, problems)
        assert any('(%s)' % req in p for p in hits), '%s: wanted %s in %s' % (name, req, hits)
        put_decisions(fx, [dec(1)])
        assert load_problems(fx) == [], name                                  # the same file, repaired, is clean


@test
@with_fixture
def decisions_file_shape_is_checked(fx):
    for raw in ('{ not json', '[]', '{"decisions": {}}', '{"decisions": [], "extra": 1}', '{}'):
        put_decisions(fx, None, raw=raw)
        problems = load_problems(fx)
        assert problems and all('decisions.json' in p and '(R5.14)' in p for p in problems), (raw, problems)
    put_decisions(fx, [])
    assert load_problems(fx) == []                                            # an empty list is a valid, empty file
    assert R.load_content(fx.record, 'artifacts')['decisions'] == []


@test
@with_fixture
def decisions_image_is_embedded_and_size_limited(fx):
    folder = os.path.join(fx.record, 'content', 'artifacts', 'assets')
    os.makedirs(folder)
    with open(os.path.join(folder, 'a.png'), 'wb') as handle:
        handle.write(PNG)
    put_decisions(fx, [dec(1, options=[opt('A', image='assets/a.png'), opt('B')], chosen='B', owner_words=None)])
    fx.reload()
    uri = fx.contents['artifacts']['decisions'][0]['options'][0]['image_uri']
    assert uri.startswith('data:image/png;base64,')
    out = fx.render('artifacts')
    assert '<img class="decision-image" src="%s" alt="A">' % uri in out
    assert fx.check(out, 'artifacts') == [] and 'http' not in out[out.index('class="decision-image"'):][:200]
    assert fx.render('artifacts') == out                                       # deterministic with images
    with open(os.path.join(folder, 'a.png'), 'wb') as handle:
        handle.write(PNG + b'\0' * R.MAX_IMAGE_BYTES)
    assert any('at most' in p and '(R5.17)' in p for p in load_problems(fx))
    os.remove(os.path.join(folder, 'a.png'))
    os.rmdir(folder)                                                           # an empty or missing assets/ folder is fine
    put_decisions(fx, [dec(1)])
    assert load_problems(fx) == []


@test
@with_fixture
def decisions_assets_folder_is_not_a_content_file(fx):
    write(os.path.join(fx.record, 'content', 'artifacts', 'assets', 'unused.png'), 'x')
    assert load_problems(fx) == []                                             # assets/ is allowed beside the sections
    write(os.path.join(fx.record, 'content', 'artifacts', 'stray.png'), 'x')
    assert any('not a content file' in p for p in load_problems(fx))


@test
@with_fixture
def decisions_hand_written_section_is_refused(fx):
    for title in ('Decisions', 'decisions', '  DECISIONS '):
        write(os.path.join(fx.record, 'content', 'models', '02-decisions.html'), '<!-- title: %s -->\n<p>Typed by hand.</p>\n' % title)
        problems = load_problems(fx, 'models')
        assert len(problems) == 1 and 'decisions.json' in problems[0] and '(R5.19)' in problems[0], problems
    write(os.path.join(fx.record, 'content', 'models', '02-decisions.html'), '<!-- title: Decisions made -->\n<p>Fine.</p>\n')
    assert load_problems(fx, 'models') == []                                   # only the exact title is drawn from the file
    os.remove(os.path.join(fx.record, 'content', 'models', '02-decisions.html'))


@test
@with_fixture
def decisions_full_progress_has_none(fx):
    write(os.path.join(fx.record, 'content', 'full-progress', 'decisions.json'), '{"decisions": []}')
    problems = load_problems(fx, 'full-progress')
    assert len(problems) == 1 and 'full-progress artifact has no decisions' in problems[0], problems


PREVIEW_BAD = [
    ('script element', '<p>x</p><script>alert(1)</script>', 'script'),
    ('style element', '<style>p{color:red}</style><p>x</p>', 'style'),
    ('iframe', '<iframe src="#"></iframe>', 'iframe'),
    ('on* attribute', '<p onclick="alert(1)">x</p>', 'onclick'),
    ('on* attribute in another case', '<img src="data:image/png;base64,AAAA" ONERROR="alert(1)">', 'onerror'),
    ('external image', '<img src="https://example.com/a.png" alt="">', 'external URL'),
    ('external image, no scheme', '<img src="//example.com/a.png" alt="">', 'external URL'),
    ('external link', '<a href="http://example.com">x</a>', 'external URL'),
    ('external URL hidden by a space', '<a href="ht tp://example.com">x</a>', 'external URL'),
    ('script URL', '<a href="javascript:alert(1)">x</a>', 'script URL'),
    ('script URL hidden by a tab', '<a href="java\tscript:alert(1)">x</a>', 'script URL'),
    ('data URL that is not an image', '<a href="data:text/html;base64,AAAA">x</a>', 'data: URL'),
    ('svg data URL', '<img src="data:image/svg+xml;base64,AAAA" alt="">', 'data: URL'),
    ('style url()', '<div style="background:url(a.png)">x</div>', 'url()'),
    ('style @import', '<div style="@import \'a.css\'">x</div>', 'url()'),
    ('fixed position', '<div style="position: fixed; top:0">x</div>', 'url()'),
    ('id attribute', '<div id="s0">x</div>', 'id'),
    ('form', '<form action="#"><input name="a"></form>', 'form'),
    ('object', '<object data="#"></object>', 'object'),
    ('a heading of the page', '<h2>Section</h2>', 'h2'),
    ('foreignObject', '<svg><foreignObject><p>x</p></foreignObject></svg>', 'foreignobject'),
    ('unclosed tag', '<div><p>x</p>', 'not closed'),
    ('section number', '<p>&sect; 3</p>', 'section number'),
]
PREVIEW_GOOD = [
    '<pre>+------+\n| Pay  |\n+------+</pre>',
    '<div style="background: #f5f5f5; padding: .5em"><b>Pay</b> <small>now</small></div>',
    '<table><tr><td>a</td><td>b</td></tr></table>',
    '<img src="data:image/png;base64,iVBORw0KGgo=" alt="mock">',
    '<a href="#s1">Section 1</a>',
    '<svg viewBox="0 0 10 10"><rect x="1" y="1" width="8" height="8"></rect></svg>',
    '<p>See https-like text: not a link.</p>',
]


@test
def decisions_previews_are_sanitised():
    for name, markup, needle in PREVIEW_BAD:
        problems = R.preview_problems(markup)
        assert problems and any(needle in p for p in problems), '%s: %s' % (name, problems)
        assert all('(R5.17)' in p or 'not closed' in p for p in problems), (name, problems)
    for markup in PREVIEW_GOOD:
        assert R.preview_problems(markup) == [], (markup, R.preview_problems(markup))


@test
@with_fixture
def decisions_a_bad_preview_fails_the_load_and_names_the_option(fx):
    for name, markup, needle in PREVIEW_BAD:
        put_decisions(fx, [dec(1, options=[opt('Single page', preview=markup), opt('Three steps')])])
        problems = load_problems(fx)
        assert problems and all("D1 option 1 preview" in p for p in problems), (name, problems)
    put_decisions(fx, [dec(1, options=[opt('Single page', preview='x' * 4001), opt('Three steps')])])
    assert any('at most 4000' in p for p in load_problems(fx))


# ---- rendering
def decision_blocks(html):
    dom = R.parse_dom(html)
    return dom, R.find_all(dom, pred=lambda n: 'data-decision' in n.attrs)


@test
@with_fixture
def decisions_render_section_before_history_and_numbered(fx):
    registry = sample(fx)
    out = fx.render('artifacts', registry=registry)
    dom = R.parse_dom(out)
    nav = [R.text_of(a) for a in R.find_all(R.find(dom, 'nav'), 'a')]
    assert nav == ['0Status and checklist', '1What and why', '2The design', '3Decisions', '4History'], nav
    sections = [(n.attrs['id'], R.text_of(R.find(n, 'h2'))) for n in R.find_all(dom, 'section')]
    assert sections[-2:] == [('s3', '§ 3Decisions'), ('s4', '§ 4History')], sections
    assert fx.check(out, 'artifacts', registry=registry) == []                 # R5.2 and the rest still hold
    # no decisions, no section; the History stays last
    plain = fx.render('models').split('</style>')[-1]
    assert 'Decisions' not in plain and 'decision' not in plain


@test
@with_fixture
def decisions_newest_first_and_replaced_collapsed(fx):
    registry = sample(fx)
    _, blocks = decision_blocks(fx.render('artifacts', registry=registry))
    assert [b.attrs['data-decision'] for b in blocks] == ['D3', 'D2', 'D1']
    assert [b.tag for b in blocks] == ['article', 'article', 'details']
    d1 = blocks[2]
    assert 'open' not in d1.attrs and 'decision-replaced' in d1.attrs['class']
    assert 'Replaced by D3' in R.text_of(R.find(d1, 'summary'))
    assert 'Replaced by' not in R.text_of(blocks[0]) and 'Replaced by' not in R.text_of(blocks[1])
    assert 'Replaces D1' in R.text_of(R.find(blocks[0], 'p', 'decision-meta'))


@test
@with_fixture
def decisions_chosen_card_chip_words_and_not_chosen(fx):
    registry = sample(fx)
    _, blocks = decision_blocks(fx.render('artifacts', registry=registry))
    d3 = blocks[0]
    cards = R.find_all(d3, 'div', 'decision-option')
    assert [R.text_of(R.find(c, 'span', 'decision-label')) for c in cards] == ['Single page', 'Wizard']
    chosen = [c for c in cards if R.has_class(c, 'decision-chosen')]
    assert len(chosen) == 1 and R.text_of(R.find(chosen[0], 'span', 'decision-label')) == 'Wizard'
    assert [R.text_of(c) for c in R.find_all(chosen[0], 'span', 'decision-chip')] == ['Chosen by the owner · 10 Oct']
    assert R.text_of(R.find(chosen[0], 'blockquote', 'decision-words')) == '“wizard, it is clearer”'
    muted = [c for c in cards if c is not chosen[0]]
    assert len(muted) == 1 and R.has_class(muted[0], 'decision-muted')
    assert [R.text_of(c) for c in R.find_all(muted[0], 'span', 'decision-chip')] == ['Not chosen']
    assert R.find(muted[0], 'blockquote') is None                              # the words belong to the chosen card only
    assert R.text_of(R.find(muted[0], 'p', 'decision-summary')) == 'Single page, in a sentence.'   # shown in full


@test
@with_fixture
def decisions_recommended_tag_whether_or_not_chosen(fx):
    registry = sample(fx)
    _, blocks = decision_blocks(fx.render('artifacts', registry=registry))
    d1, d3 = blocks[2], blocks[0]
    d1_tags = [(R.text_of(R.find(c, 'span', 'decision-label')), [R.text_of(t) for t in R.find_all(c, 'span', 'decision-tag')])
               for c in R.find_all(d1, 'div', 'decision-option')]
    assert d1_tags == [('Single page', ['Recommended']), ('Three steps', [])]       # recommended and chosen
    d3_tags = [(R.text_of(R.find(c, 'span', 'decision-label')), [R.text_of(t) for t in R.find_all(c, 'span', 'decision-tag')])
               for c in R.find_all(d3, 'div', 'decision-option')]
    assert d3_tags == [('Single page', []), ('Wizard', ['Recommended'])]
    # a recommended option that was not chosen keeps its tag, and the chosen one is not tagged
    put_decisions(fx, [dec(1, chosen='Three steps', owner_words=None)])
    fx.reload()
    _, blocks = decision_blocks(fx.render('artifacts'))
    cards = R.find_all(blocks[0], 'div', 'decision-option')
    assert R.has_class(cards[0], 'decision-muted') and R.text_of(R.find(cards[0], 'span', 'decision-tag')) == 'Recommended'
    assert R.has_class(cards[1], 'decision-chosen') and R.find(cards[1], 'span', 'decision-tag') is None


@test
@with_fixture
def decisions_open_shows_needs_you_and_no_chosen_card(fx):
    registry = sample(fx)
    out = fx.render('artifacts', registry=registry)
    _, blocks = decision_blocks(out)
    d2 = blocks[1]
    assert [R.text_of(c) for c in R.find_all(R.find(d2, 'h3'), 'span', 'status-needs-you')] == ['Needs you']
    assert R.find_all(d2, 'div', 'decision-chosen') == [] and R.find_all(d2, 'span', 'decision-chip') == []
    assert all(not R.has_class(c, 'decision-muted') for c in R.find_all(d2, 'div', 'decision-option'))
    assert 'Decided' not in R.text_of(R.find(d2, 'p', 'decision-meta')) and 'Task AR7' in R.text_of(R.find(d2, 'p', 'decision-meta'))
    # the replaced decision and the closed ones carry no Needs you chip
    assert R.find_all(blocks[0], 'span', 'status-needs-you') == [] and R.find_all(blocks[2], 'span', 'status-needs-you') == []


@test
@with_fixture
def decisions_text_is_escaped_and_previews_kept(fx):
    registry = sample(fx, [dec(1, question='A <b>bold</b> & "quoted" question?', owner_words='<i>mine</i>',
                               options=[opt('A & B', summary='<script>x</script>', preview='<pre>a &lt; b</pre>'), opt('C')],
                               chosen='A & B')])
    out = fx.render('artifacts', registry=registry)
    assert 'A &lt;b&gt;bold&lt;/b&gt; &amp; &quot;quoted&quot; question?' in out
    assert '&lt;script&gt;x&lt;/script&gt;' in out and '<script>x' not in out
    assert '&ldquo;&lt;i&gt;mine&lt;/i&gt;&rdquo;' in out
    assert '<div class="decision-preview"><pre>a &lt; b</pre></div>' in out
    assert fx.check(out, 'artifacts', registry=registry) == []


@test
@with_fixture
def decisions_render_adds_no_script_and_is_deterministic(fx):
    registry = sample(fx)
    out = fx.render('artifacts', registry=registry)
    assert out == fx.render('artifacts', registry=registry)
    assert out.count('<script') == 1                                           # only the template's own theme script (R5.9)
    assert fx.check(out, 'artifacts', registry=registry) == []


@test
@with_fixture
def decisions_lede_lists_open_decisions(fx):
    registry = sample(fx)
    out = fx.render('artifacts', registry=registry)
    assert glance(out)['you'][:2] == (['AR7'], ['D2']), glance(out)['you']        # tasks first, then decisions
    assert 'D2</span>Should History also list decisions?' in out
    assert R.needs_you_sentence(registry['tasks'], R.open_decisions(fx.contents['artifacts']['decisions'])).endswith('decisions?')
    registry2 = copy.deepcopy(registry)
    registry2['tasks'][2]['status'] = 'To do'
    out2 = fx.render('artifacts', registry=registry2)
    assert glance(out2)['you'][:2] == ([], ['D2'])
    # a replaced open decision, and a decided one, are not listed
    put_decisions(fx, [open_dec(1), dec(2, replaces='D1')])
    fx.reload()
    assert glance(fx.render('artifacts'))['you'] == ([], [], '', 'Nothing needs you.')
    # the existing sentence is unchanged without decisions
    assert R.needs_you_sentence([{'id': 'AR1', 'status': 'Needs you', 'item': 'Sign off'}]) == 'Needs you: AR1 Sign off.'
    assert R.needs_you_sentence([]) == 'Nothing needs you.'
    assert R.needs_you_sentence([], [open_dec(4), open_dec(5, question='Which name?')]) == \
        'Needs you: D4 Should History also list decisions?; D5 Which name?'


@test
@with_fixture
def decisions_full_progress_line_counts_open_decisions(fx):
    registry = sample(fx)
    def cells(out):
        s1 = R.find(R.parse_dom(out), 'section', pred=lambda n: n.attrs.get('id') == 's1')
        return [[R.text_of(td) for td in R.find_all(tr, 'td')] for tr in R.find_all(s1, 'tr', pred=lambda n: R.find(n, 'td'))]
    out = fx.render('full-progress', registry=registry)
    assert cells(out)[0] == ['Feature: Project artifacts standard', '10 Oct 12:39', 'AR5 to AR16',
                            '1 Running1 Needs you2 Built1 open decision', 'The design is agreed. 1 decision open.']
    assert cells(out)[1][4] == 'Effort question is live!'
    assert fx.check(out, 'full-progress', registry=registry) == []
    put_decisions(fx, [open_dec(1), open_dec(2), dec(3)])
    fx.reload()
    assert cells(fx.render('full-progress'))[0][4] == 'The design is agreed. 2 decisions open.'
    put_decisions(fx, [dec(1)])
    fx.reload()
    assert cells(fx.render('full-progress'))[0][4] == 'The design is agreed.'


# ---- check_html: each Decisions check fires alone
def reverse_decisions(html):
    """The three sample decisions in oldest-first order, each block untouched."""
    i3 = html.index('<article class="decision decision-decided" data-decision="D3">')
    i2 = html.index('<article class="decision decision-open" data-decision="D2">')
    i1 = html.index('<details class="decision decision-replaced" data-decision="D1">')
    end = html.index('\n</div>\n</section>', i1)
    return html[:i3] + html[i1:end] + '\n' + html[i2:i1] + html[i3:i2].rstrip('\n') + html[end:]


def mutate_cases(fx):
    """(name, expected requirement, function html -> html) on the sample's rendering."""
    return [
        ('chosen mark removed', 'R5.22', lambda h: h.replace('decision-option decision-chosen', 'decision-option decision-muted', 1)),
        ('chosen chip names the wrong date', 'R5.22', lambda h: sub1(h, 'Chosen by the owner &middot; 10 Oct', 'Chosen by the owner &middot; 11 Oct', 2)),
        ('Not chosen chip dropped', 'R5.22', lambda h: h.replace('Not chosen', 'Skipped', 1)),
        ('owner words dropped', 'R5.22', lambda h: sub1(h, '<blockquote class="decision-words">&ldquo;wizard, it is clearer&rdquo;</blockquote>', '')),
        ('Recommended tag dropped', 'R5.22', lambda h: h.replace('<span class="decision-tag">Recommended</span>', '', 1)),
        ('Needs you chip dropped from the open decision', 'R5.23',
         lambda h: sub1(h, ' <span class="status-chip status-needs-you">Needs you</span></h3>', '</h3>')),
        ('replaced decision not collapsed', 'R5.23', lambda h: uncollapse_replaced(h)),
        ('replaced decision opened', 'R5.23', lambda h: sub1(h, '<details class="decision decision-replaced" ', '<details open class="decision decision-replaced" ')),
        ('replaced-by line names the wrong decision', 'R5.23', lambda h: sub1(h, 'Replaced by D3', 'Replaced by D2')),
        ('decision order reversed', 'R5.20', reverse_decisions),
        ('question changed', 'R5.21', lambda h: sub1(h, 'Which layout, second thoughts?', 'Which layout, third thoughts?')),
        ('option card dropped', 'R5.21', lambda h: sub1(h, '<span class="decision-label">Wizard</span>', '<span class="decision-label">Winzard</span>')),
    ]


@test
@with_fixture
def decisions_every_check_html_rule_fires_alone(fx):
    registry = sample(fx)
    clean = fx.render('artifacts', registry=registry)
    assert fx.check(clean, 'artifacts', registry=registry) == []
    for name, req, fn in mutate_cases(fx):
        got = fx.check(fn(clean), 'artifacts', registry=registry)
        assert req in reqs(got), '%s: wanted %s, got %s' % (name, req, got)
        assert set(reqs(got)) <= {req}, '%s: wanted only %s, got %s' % (name, req, got)


@test
@with_fixture
def decisions_section_position_and_presence_are_checked(fx):
    registry = sample(fx)
    clean = fx.render('artifacts', registry=registry)
    # the Decisions section renamed: it is no longer found just before History
    renamed = sub1(clean, '</span>Decisions</h2>', '</span>Choices</h2>')
    renamed = sub1(renamed, '<b>3</b>Decisions</a>', '<b>3</b>Choices</a>')
    assert 'R5.20' in reqs(fx.check(renamed, 'artifacts', registry=registry))
    # decisions.json empty but the section still in the HTML
    put_decisions(fx, [])
    fx.reload()
    assert 'R5.20' in reqs(fx.check(clean, 'artifacts', registry=registry))
    # a Decisions section on the full-progress artifact is not drawn from any file
    fp = fx.render('full-progress')
    forged = sub1(fp, '</span>How it stays current</h2>', '</span>Decisions</h2>')
    forged = sub1(forged, '<b>2</b>How it stays current</a>', '<b>2</b>Decisions</a>')
    assert 'R5.20' not in reqs(fx.check(forged, 'full-progress'))            # only features have a generated Decisions section


@test
@with_fixture
def decisions_lede_check_catches_a_missing_open_decision(fx):
    registry = sample(fx)
    clean = fx.render('artifacts', registry=registry)
    bad = drop_item(clean, 'decision', 'D2')
    assert 'R5.7' in reqs(fx.check(bad, 'artifacts', registry=registry))


@test
def decisions_css_is_structure_only_and_phone_ready():
    import re
    css = R.structure_css(PLUGIN)
    for selector in ('.decision-options', '.decision-option.decision-chosen', '.decision-option.decision-muted', '.decision-chip-chosen',
                     '.decision-chip-muted', '.decision-tag', '.decision-words', 'details.decision-replaced', '.decision-preview',
                     '.decision-image'):
        assert selector in css, selector
    # one column on a phone: a media query that sets the options grid to a single track, and auto-fit tracks that cannot fit two
    assert re.search(r'@media \(max-width: 40rem\)\s*\{[^}]*\.decision-options\s*\{\s*grid-template-columns:\s*1fr', css)
    assert 'minmax(min(100%, 17rem), 1fr)' in css
    block = css[css.index('/* Decisions'):css.index('/* Phone width */')]
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(', block)       # tokens only
    assert 'var(--signal)' in block and 'var(--on-signal)' in block and 'var(--surface-2)' in block


# ------------------------------------------------------------------ AR40: At a glance
def glance_registry():
    """Fixture registry plus ten Live tasks changed within 24 h of the stamp, and one just outside it."""
    registry = base_registry()
    for n in range(10):
        registry['tasks'].append(task('LV%d' % (n + 1), 'project', 'Live', 'Shipped %d' % (n + 1), '10 Oct',
                                      '2026-10-10T%02d:00+01:00' % (n + 1), 'luismc-project-setup'))
    registry['tasks'].append(task('LV11', 'project', 'Live', 'Shipped long ago', '08 Oct', '2026-10-09T12:00+01:00'))   # 24 h 39 min: out
    return registry


QUIET = {'spec': R.SPEC, 'updated': STAMP_ISO, 'tasks': [
    task('MP1', 'models', 'Live', 'Role rules', '08 Oct', '2026-10-08T10:00+01:00')]}


@test
@with_fixture
def at_a_glance_groups_and_order(fx):
    """R5.33, R5.34: the groups, in order, each from its statuses; To do is not listed; Live is 24 h and capped at 8."""
    out = fx.render('full-progress', registry=glance_registry())
    got = glance(out)
    assert list(got) == ['you', 'running', 'built', 'waiting', 'live'], list(got)
    assert got['you'][0] == ['DS9', 'DS11'] and got['running'][0] == ['DS6', 'AR6', 'MP2'], got
    assert got['built'][0] == ['AR5', 'AR16'] and got['waiting'][0] == ['DS7', 'DS10'], got
    assert got['live'][0] == ['LV10', 'LV9', 'LV8', 'LV7', 'LV6', 'LV5', 'LV4', 'LV3'] and got['live'][2] == 'and 2 more', got['live']
    assert 'AR7' not in str(got) and 'DS8' not in str(got)                                   # To do
    # the line: id, item, then the Expected for open statuses
    row = out[out.index('data-glance-task="DS6"'):]
    row = row[:row.index('</li>')]
    assert '<span class="glance-expected">10 Oct ~13:45</span>' in row, row
    fx.registry = glance_registry()
    by_id = {t['id']: t for t in fx.registry['tasks']}
    by_id['AR6']['expected_basis'] = 'agent slot'
    by_id['LV10']['expected_basis'] = 'not shown'
    out = fx.render('artifacts')
    assert '<span class="glance-basis">agent slot</span>' in out and 'not shown' not in out
    assert fx.check(out, 'artifacts') == []
    assert fx.check(fx.render('full-progress'), 'full-progress') == []
    # an empty group is omitted, and Needs you always shows
    out = fx.render('models', registry=QUIET)
    assert list(glance(out)) == ['you'] and glance(out)['you'] == ([], [], '', 'Nothing needs you.')
    assert fx.check(out, 'models', registry=QUIET) == []


@test
@with_fixture
def glance_splits_owner_waits_from_work_waits(fx):
    """R5.34, R5.34a: a Waiting task with waits_on owner is in Needs you, after Needs you and before Failed; the others
    stay in Waiting for other work; each of their rows reads the dependency first, then the item, then Expected."""
    registry = glance_registry()
    by_id = {t['id']: t for t in registry['tasks']}
    by_id['DS7']['waits_on'] = 'owner'
    by_id['DS7']['expected_basis'] = 'your OK on the folder name'
    by_id['DS10']['detail'] = 'Needs the cloud runner. More text.'
    by_id['DS9']['expected_basis'] = 'your review'
    out = fx.render('full-progress', registry=registry)
    got = glance(out)
    assert got['you'][0] == ['DS9', 'DS7', 'DS11'], got['you']
    assert got['waiting'][0] == ['DS10'], got['waiting']
    assert R.GLANCE_GROUPS[4 - 1] == ('waiting', 'Waiting for other work') and 'Waiting or on hold' not in out
    row = out[out.index('data-glance-task="DS7"'):]
    row = row[:row.index('</li>')]
    assert row.index('glance-dep') < row.index('docs/ folder rule') < row.index('glance-expected'), row
    assert '<span class="glance-dep">your OK on the folder name</span>' in row and 'glance-basis' not in row, row
    row = out[out.index('data-glance-task="DS10"'):]
    assert '<span class="glance-dep">Needs the cloud runner.</span>' in row[:row.index('</li>')], row
    assert fx.check(out, 'full-progress', registry=registry) == []
    # the work side with no basis and no detail sentence falls back to the release it rides
    by_id['DS10']['detail'] = ''
    by_id['DS10']['rides'] = 'DS6'
    by_id['DS6']['release'] = True
    assert R.glance_dependency(by_id['DS10'], by_id) == R.release_name(by_id['DS6'])


@test
@with_fixture
def glance_default_waits_on_work_keeps_old_grouping(fx):
    """R5.34a: without waits_on a Waiting or On hold task is waiting for other work, as before the split; Needs you
    and its count do not change."""
    out = fx.render('full-progress', registry=glance_registry())
    got = glance(out)
    assert got['you'][0] == ['DS9', 'DS11'] and got['waiting'][0] == ['DS7', 'DS10'], got
    assert R.waits_on_owner({'status': 'Waiting', 'waits_on': 'work'}) is False
    assert R.waits_on_owner({'status': 'Running', 'waits_on': 'owner'}) is False


@test
@with_fixture
def glance_needs_you_count_matches_the_section(fx):
    """R5.34a, R6.13: the Needs you count is the section: Needs you, owner waits, Failed and open decisions; the
    summary line and the Needs you sentence agree."""
    registry = glance_registry()
    by_id = {t['id']: t for t in registry['tasks']}
    by_id['DS7']['waits_on'] = 'owner'
    by_id['DS10']['waits_on'] = 'owner'
    out = fx.render('full-progress', registry=registry)
    dom = R.parse_dom(out)
    groups = {g.attrs['data-glance']: g for g in R.find_all(dom, 'details', 'glance-group')}
    assert R.text_of(R.find(groups['you'], 'span', 'fold-count')) == '4 tasks'
    assert 'waiting' not in groups                                                             # nothing else waits on work
    assert glance(out)['you'][0] == ['DS9', 'DS7', 'DS10', 'DS11']
    assert R.needs_you_sentence(registry['tasks']).startswith('Needs you: DS9 ')
    assert 'DS7' in R.needs_you_sentence(registry['tasks'])
    assert R.feature_summary([by_id['DS7']]) == '1 needs you' and R.feature_summary([by_id['DS6']]).startswith('1 running')
    assert fx.check(out, 'full-progress', registry=registry) == []


@test
@with_fixture
def check_finds_a_wrong_split_or_dependency(fx):
    """R5.34a, R5.35: a task in the wrong one of the two groups, or a row without its dependency, is a finding."""
    registry = glance_registry()
    by_id = {t['id']: t for t in registry['tasks']}
    by_id['DS7']['waits_on'] = 'owner'
    by_id['DS7']['expected_basis'] = 'your OK'
    out = fx.render('full-progress', registry=registry)
    expect(fx, sub1(out, '<span class="glance-dep">your OK</span> ', ''), 'full-progress', ['R5.34a'], registry=registry)
    expect(fx, drop_item(out, 'task', 'DS7'), 'full-progress', ['R5.7'], registry=registry)
    by_id['DS7']['waits_on'] = 'work'
    expect(fx, out, 'full-progress', ['R5.7', 'R5.9', 'R5.35', 'R6.13'], registry=registry)           # rendered with the old split


@test
@with_fixture
def at_a_glance_is_deterministic_and_placed(fx):
    """R5.33: after the lede, before the tiles; same bytes each time (R7.4)."""
    out = fx.render('artifacts')
    assert out == fx.render('artifacts')
    assert out.index('class="lede"') < out.index('class="at-a-glance"') < out.index('class="status-count-tiles"')


@test
@with_fixture
def check_r532_block_and_order(fx):
    """R5.3 (order, lede optional) and R5.33 (groups in order)."""
    out = fx.render('artifacts')
    start = out.index('<div class="at-a-glance">')
    end = out.index('</details>\n</div>', start) + len('</details>\n</div>')
    block = out[start:end]
    after_tiles = sub1(out[:start] + out[end:], '<p class="note">Key:', block + '\n<p class="note">Key:')
    expect(fx, after_tiles, 'artifacts', ['R5.3'])                                           # block after the tiles
    expect(fx, out[:start] + out[end:], 'artifacts', ['R5.3'])                               # block missing
    lede = out[out.index('<p class="lede">'):out.index('</p>', out.index('<p class="lede">')) + 4]
    lede_late = sub1(out, lede + '\n', '')
    lede_late = sub1(lede_late, block, block + '\n' + lede)
    expect(fx, lede_late, 'artifacts', ['R5.3'])                                             # lede after the block
    expect(fx, sub1(out, lede + '\n', ''), 'artifacts', [])                                  # no lede: still clean
    swapped = (out.replace('data-glance="running"', 'data-glance="TMP"').replace('data-glance="built"', 'data-glance="running"')
               .replace('data-glance="TMP"', 'data-glance="built"'))
    expect(fx, swapped, 'artifacts', ['R5.33', 'R5.35', 'R6.13'])


@test
@with_fixture
def check_r534_each_group_lists_its_tasks(fx):
    """R5.34, R5.35: a missing or extra task in a group, or a wrong 'and N more', is a finding."""
    fx.registry = glance_registry()
    fp = fx.render('full-progress')
    expect(fx, drop_item(fp, 'task', 'DS6'), 'full-progress', ['R5.35'])                     # Running task missing
    expect(fx, drop_item(fp, 'task', 'AR5'), 'full-progress', ['R5.35'])                     # Built task missing
    expect(fx, drop_item(fp, 'task', 'DS10'), 'full-progress', ['R5.35'])                    # On hold task missing
    expect(fx, drop_item(fp, 'task', 'LV9'), 'full-progress', ['R5.35'])                     # Live task missing
    expect(fx, sub1(fp, 'and 2 more', 'and 3 more'), 'full-progress', ['R5.35'])
    extra = sub1(fp, '<li data-glance-task="AR5">', '<li data-glance-task="AR7"><span class="task-id">AR7</span>x</li>\n<li data-glance-task="AR5">')
    expect(fx, extra, 'full-progress', ['R5.35'])                                            # To do task listed
    old_live = sub1(fp, '<li data-glance-task="LV3">', '<li data-glance-task="LV11"><span class="task-id">LV11</span>x</li>\n<li data-glance-task="LV3">')
    expect(fx, old_live, 'full-progress', ['R5.35'])                                         # Live task older than 24 h listed
    # the window follows the stamp: exactly 24 h before it is in
    fx.registry['tasks'][-1]['changed'] = '2026-10-09T12:39+01:00'
    assert 'LV11' not in glance(fx.render('full-progress'))['live'][0]                     # cut by the cap, still not shown past 8
    assert fx.check(fx.render('full-progress'), 'full-progress') == []


@test
@with_fixture
def lede_is_a_short_optional_note(fx):
    """R5.7, R5.37: an empty lede renders no paragraph; over 300 characters warns, never fails."""
    folder = os.path.join(fx.record, 'content', 'artifacts')
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'artifacts', 'hero': 'h', 'lede': '', 'extra_css': ''}))
    fx.reload()
    out = fx.render('artifacts')
    assert 'class="lede"' not in out and fx.check(out, 'artifacts') == []
    assert R.lede_warnings(fx.contents['artifacts']) == []
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'artifacts', 'hero': 'h', 'lede': 'Word. ' * 60, 'extra_css': ''}))
    fx.reload()
    warned = R.lede_warnings(fx.contents['artifacts'])
    assert len(warned) == 1 and 'one or two sentences' in warned[0] and 'At a glance' in warned[0], warned
    assert fx.check(fx.render('artifacts'), 'artifacts') == []                              # a warning, not a finding
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'artifacts', 'hero': 'h', 'lede': 'x' * 300, 'extra_css': ''}))
    fx.reload()
    assert R.lede_warnings(fx.contents['artifacts']) == []


@test
@with_fixture
def section_one_never_blank(fx):
    """R5.36: a feature with an empty lede gets its generated summary in Where it stands."""
    folder = os.path.join(fx.record, 'content', 'models')
    write(os.path.join(folder, 'meta.json'), json.dumps({'title': 'models', 'hero': 'h', 'lede': '', 'extra_css': ''}))
    fx.reload()
    out = fx.render('full-progress')
    s1 = R.find(R.parse_dom(out), 'section', pred=lambda n: n.attrs.get('id') == 's1')
    cells = [[R.text_of(td) for td in R.find_all(tr, 'td')] for tr in R.find_all(s1, 'tr', pred=lambda n: R.find(n, 'td'))]
    assert cells[1][4] == '1 running, 2 live, nothing needs you.', cells
    assert R.feature_summary([task('X1', 'a', 'Needs you', 'i', '10 Oct')]) == '1 needs you'
    assert fx.check(out, 'full-progress') == []


@test
def at_a_glance_css_uses_tokens_and_fits_a_phone():
    import re
    css = R.structure_css(PLUGIN)
    for selector in ('.at-a-glance', '.glance-group', '.glance-label', '.glance-you', '.glance-running', '.glance-expected', '.glance-more'):
        assert selector in css, selector
    block = css[css.index('.at-a-glance {'):css.index('/* Status chips */')]
    assert 'var(--signal)' in block and 'var(--running-bg)' in block and 'var(--waiting-bg)' in block and 'var(--ink-muted)' in block
    assert not re.search(r'#[0-9a-fA-F]{3,6}\b', block), 'colours must be tokens'
    assert 'grid-template-columns' not in block, 'the groups are stacked blocks, so a phone never scrolls sideways'
    assert 'min-height: 2.75rem' in css[css.index('details.glance-group > summary,'):css.index('details.glance-group > summary::-webkit')]


def _s1_rows(out):
    s1 = R.find(R.parse_dom(out), 'section', pred=lambda n: n.attrs.get('id') == 's1')
    return [[R.text_of(td) for td in R.find_all(tr, 'td')] for tr in R.find_all(s1, 'tr', pred=lambda n: R.find(n, 'td'))]


def _feature_fold(out, gkey):
    return [f for f in R.find_all(R.parse_dom(out), 'details', 'feature-group') if f.attrs['data-group'] == 'features-' + gkey][0]


def _fold_titles(out):
    return [R.text_of(R.find(f, 'strong')) for f in R.find_all(R.parse_dom(out), 'details', 'feature-group')]


def _set_models(fx, status):
    reg = copy.deepcopy(fx.registry)
    for t in reg['tasks']:
        if t['owner'] == 'models':
            t['status'], t['expected'] = status, '09 Oct'
    return reg


@test
@with_fixture
def feature_artifacts_split_mixed_states(fx):
    """R5.50: not complete features in an open fold, complete ones in a closed fold, counts in the titles, one table each."""
    reg = _set_models(fx, 'Live')
    out = fx.render('full-progress', registry=reg)
    assert _fold_titles(out) == ['Feature artifacts in progress (1)', 'Complete feature artifacts (1)']
    progress, complete = _feature_fold(out, 'progress'), _feature_fold(out, 'complete')
    assert 'open' in progress.attrs and 'open' not in complete.attrs                  # open by default / closed by default
    assert R.has_class(progress, 'status-fold') and R.has_class(complete, 'status-fold')   # the page's own collapsible element
    assert [R.text_of(a) for a in R.find_all(progress, 'a')] == ['Feature: Project artifacts standard']
    assert [R.text_of(a) for a in R.find_all(complete, 'a')] == ['Feature: Model and effort profiles']
    for fold in (progress, complete):
        assert len(R.find_all(fold, 'table', 'feature-list')) == 1 and len(R.find_all(fold, 'button', 'sort-header')) == 2
    assert fx.check(out, 'full-progress', registry=reg) == []
    assert len(R.find_all(R.parse_dom(out), 'section')) >= 2 and R.text_of(R.find_all(R.parse_dom(out), 'h2')[1]).endswith('Feature artifacts')


@test
@with_fixture
def feature_artifacts_split_all_complete(fx):
    """R5.50: with every feature complete the in-progress fold says so in one line and holds no table."""
    reg = copy.deepcopy(fx.registry)
    keys = {e['key'] for e in fx.manifest['feature_artifacts']}
    for t in reg['tasks']:
        if t['owner'] in keys:
            t['status'], t['expected'] = 'Live', '09 Oct'
    out = fx.render('full-progress', registry=reg)
    titles = _fold_titles(out)
    assert titles[0] == 'Feature artifacts in progress (0)', titles
    progress = _feature_fold(out, 'progress')
    assert R.find(progress, 'table') is None
    assert [R.text_of(p) for p in R.find_all(progress, 'p', 'feature-none')] == ['No feature artifacts in progress.']
    assert titles[1] == 'Complete feature artifacts (2)' and 'open' not in _feature_fold(out, 'complete').attrs
    assert fx.check(out, 'full-progress', registry=reg) == []


@test
@with_fixture
def feature_artifacts_split_none_complete(fx):
    """R5.50: with no complete feature the complete fold is closed, says so in one line and holds no table."""
    out = fx.render('full-progress')
    assert _fold_titles(out) == ['Feature artifacts in progress (2)', 'Complete feature artifacts (0)']
    complete = _feature_fold(out, 'complete')
    assert 'open' not in complete.attrs and R.find(complete, 'table') is None
    assert [R.text_of(p) for p in R.find_all(complete, 'p', 'feature-none')] == ['No feature artifacts are complete yet.']
    assert R.text_of(R.find(complete, 'span', 'fold-count')) == '0 feature artifacts'
    assert fx.check(out, 'full-progress') == []


@test
@with_fixture
def feature_artifacts_split_checker_finds_faults(fx):
    """R5.50: the checker refuses a wrong default state, a wrong count and a feature in the wrong fold."""
    reg = _set_models(fx, 'Live')
    out = fx.render('full-progress', registry=reg)
    closed = out.replace('data-group="features-progress" open', 'data-group="features-progress"', 1)
    assert 'R5.50' in reqs(fx.check(closed, 'full-progress', registry=reg))
    wrong = out.replace('Complete feature artifacts (1)', 'Complete feature artifacts (5)', 1)
    assert 'R5.50' in reqs(fx.check(wrong, 'full-progress', registry=reg))
    assert 'R5.50' in reqs(fx.check(out, 'full-progress'))          # the registry says models is not complete


@test
@with_fixture
def section_one_orders_by_last_updated_newest_first(fx):
    """R5.6, R5.39: four columns, a time per feature, the newest page on top, ties by title."""
    out = fx.render('full-progress')
    dom = R.parse_dom(out)
    heads = R.find_all(R.find(dom, 'table', 'feature-list'), 'th')
    assert [R.text_of(h).rstrip(' ↑↓') for h in heads] == ['Feature artifact', 'Last updated', 'Tasks', 'State', 'Where it stands']
    assert heads[1].attrs['aria-sort'] == 'descending' and 'aria-sort' not in heads[0].attrs
    assert R.text_of(heads[1]).endswith('↓')
    assert [b.attrs['data-sort'] for b in R.find_all(dom, 'button', 'sort-header')] == ['name', 'updated']
    assert [r[0] for r in _s1_rows(out)] == ['Feature: Project artifacts standard', 'Feature: Model and effort profiles']
    manifest = base_manifest()
    manifest['feature_artifacts'][1]['updated'] = '2026-10-11T12:08+01:00'                   # models changed last
    out = fx.render('full-progress', manifest=manifest)
    assert [r[:2] for r in _s1_rows(out)] == [['Feature: Model and effort profiles', '11 Oct 12:08'],
                                              ['Feature: Project artifacts standard', '10 Oct 12:39']]
    assert fx.check(out, 'full-progress', manifest=manifest) == []
    manifest['feature_artifacts'][1]['updated'] = manifest['feature_artifacts'][0]['updated']    # a tie: by title
    out = fx.render('full-progress', manifest=manifest)
    assert [r[0] for r in _s1_rows(out)] == ['Feature: Model and effort profiles', 'Feature: Project artifacts standard']
    # another offset: compared as instants, not as text
    manifest['feature_artifacts'][0]['updated'] = '2026-10-10T12:39+00:00'
    manifest['feature_artifacts'][1]['updated'] = '2026-10-10T12:00-01:00'                   # 13:00 UTC, newer
    out = fx.render('full-progress', manifest=manifest)
    assert [r[0] for r in _s1_rows(out)] == ['Feature: Model and effort profiles', 'Feature: Project artifacts standard']
    assert fx.check(out, 'full-progress', manifest=manifest) == []


@test
@with_fixture
def section_one_reads_an_older_record_from_the_feature_file(fx):
    """R4.30: a manifest entry without `updated` takes the stamp of the feature file."""
    manifest = base_manifest()
    for entry in manifest['feature_artifacts']:
        del entry['updated']
    assert [r[1] for r in _s1_rows(fx.render('full-progress', manifest=manifest))] == ['', '']      # no file yet
    write(os.path.join(fx.record, MP_FILE), '<p>x</p><time datetime="2026-10-11T08:05+01:00">11 Oct 08:05</time>')
    out = fx.render('full-progress', manifest=manifest)
    assert [r[:2] for r in _s1_rows(out)] == [['Feature: Model and effort profiles', '11 Oct 08:05'],
                                              ['Feature: Project artifacts standard', '']]
    assert fx.check(out, 'full-progress', manifest=manifest) == []


@test
@with_fixture
def check_r539_sort_headers_and_order(fx):
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, 'data-sort="updated"', 'data-sort="date"'), 'full-progress', ['R5.39'])
    expect(fx, sub1(fp, ' aria-sort="descending"', ''), 'full-progress', ['R5.39'])
    def in_table(new):                       # the second such time: the first is the page's stamp
        cut = fp.rindex('<time datetime="2026-10-10T12:39+01:00">10 Oct 12:39</time>')
        return fp[:cut] + new + fp[cut + len('<time datetime="2026-10-10T12:39+01:00">10 Oct 12:39</time>'):]
    expect(fx, in_table('<time datetime="2026-10-08T12:39+01:00">08 Oct 12:39</time>'), 'full-progress', ['R5.6', 'R5.39'])                                                          # wrong time, and out of order
    expect(fx, in_table('<time datetime="2026-10-10T12:39+01:00">10 Oct 12:40</time>'), 'full-progress', ['R5.6'])
    expect(fx, sub1(fp, '<th>Tasks</th>', '<th>Task IDs</th>'), 'full-progress', ['R5.6'])


@test
@with_fixture
def feature_page_says_when_full_progress_was_published(fx):
    """R5.38: under the stamp, omitted before the first publish."""
    plain = fx.render('artifacts')
    assert '<p class="full-progress-published"' not in plain
    manifest = base_manifest()
    manifest['full_progress_artifact']['published_at'] = '2026-10-11T12:08+01:00'
    manifest['full_progress_artifact']['url'] = ''
    assert '<p class="full-progress-published"' not in fx.render('artifacts', manifest=manifest)                  # no URL yet
    manifest['full_progress_artifact']['url'] = FP_URL
    out = fx.render('artifacts', manifest=manifest)
    line_html = '<p class="full-progress-published">Full Progress published: <a href="%s">11 Oct 12:08</a> (Lisbon)</p>\n' % FP_URL
    assert out.count(line_html) == 1 and out.replace(line_html, '') == plain       # nothing else on the page moves, not even the stamp
    s0 = R.find(R.parse_dom(out), 'section')
    kids = [n for n in s0.children if n.tag != '#text']
    assert R.has_class(kids[1], 'last-update') and R.has_class(kids[2], 'full-progress-published')   # right under the stamp
    assert fx.check(out, 'artifacts', manifest=manifest) == []
    expect(fx, plain, 'artifacts', ['R5.38'], manifest=manifest)                                       # the line is missing
    expect(fx, out, 'artifacts', ['R5.38'])                                                            # the manifest has no such publish
    expect(fx, sub1(out, '>11 Oct 12:08<', '>11 Oct 12:09<'), 'artifacts', ['R5.38'], manifest=manifest)
    assert '<p class="full-progress-published"' not in fx.render('full-progress', manifest=manifest)


@test
@with_fixture
def full_progress_sort_script(fx):
    """R5.39: the template's script sorts the rows on a click and keeps the arrow and aria-sort."""
    import subprocess
    text = open(os.path.join(PLUGIN, 'templates', 'full-progress-artifact.html'), encoding='utf-8').read()
    start, end = text.index('    // Section 1: click'), text.index("    window.addEventListener('scroll'")
    node = shutil.which('node')
    if not node:
        assert 'sortRows' in text[start:end]
        return
    harness = r"""
function el(attrs) { return {attrs: attrs || {}, listeners: {}, textContent: '',
  getAttribute: function (k) { return k in this.attrs ? this.attrs[k] : null; },
  setAttribute: function (k, v) { this.attrs[k] = v; }, removeAttribute: function (k) { delete this.attrs[k]; },
  addEventListener: function (n, f) { this.listeners[n] = f; }, querySelector: function () { return this.arrow; }}; }
function row(name, minutes) { return {name: name, cells: [el({'data-value': name}), el({'data-value': String(minutes)})]}; }
var rows = [row('b', 30), row('a', 30), row('c', 10), row('d', 20)];
var body = {rows: rows, appendChild: function (r) { rows.splice(rows.indexOf(r), 1); rows.push(r); }};
var heads = [el({}), el({'aria-sort': 'descending'})];
var buttons = [el({'data-sort': 'name'}), el({'data-sort': 'updated'})];
buttons.forEach(function (b, i) { b.parentNode = heads[i]; b.arrow = el({}); });
var table = {tBodies: [body], querySelectorAll: function () { return buttons; }};
var document = {querySelectorAll: function () { return [table]; }};
function order() { return rows.map(function (r) { return r.name; }).join(''); }
function click(i) { buttons[i].listeners.click(); }
var out = [];
SCRIPT
click(1); out.push(order(), heads[1].attrs['aria-sort'], buttons[1].arrow.textContent);
click(1); out.push(order(), heads[1].attrs['aria-sort']);
click(0); out.push(order(), heads[0].attrs['aria-sort'], heads[1].attrs['aria-sort'] || '-', buttons[0].arrow.textContent, buttons[1].arrow.textContent === '');
click(0); out.push(order(), heads[0].attrs['aria-sort']);
click(1); out.push(order(), heads[1].attrs['aria-sort']);
console.log(JSON.stringify(out));
""".replace('SCRIPT', text[start:end])
    done = subprocess.run([node, '-e', harness], capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == ['cdab', 'ascending', '↑', 'abdc', 'descending',
                                       'abcd', 'ascending', '-', '↑', True, 'dcba', 'descending', 'abdc', 'descending'], done.stdout


# ------------------------------------------------------------------ release timeline and State column (R5.40 to R5.44)
def phase(name, start, end):
    return {'name': name, 'start': '2026-10-10T%s+01:00' % start, 'end': '2026-10-10T%s+01:00' % end}


def release(tid, item, expected, phases=None, risk=None, status='Running', number=None):
    row = task(tid, 'project', status, item, expected, '2026-10-10T12:00+01:00', 'luismc-artifacts')
    row['release'] = number or int(tid[2:]) - 50       # DS51 is RELEASE-1, DS52 RELEASE-2 (R5.45)
    if phases:
        row['phases'] = phases
    if risk:
        row['risk'] = risk
    return row


def with_releases(fx, *rows, rides=()):
    registry = copy.deepcopy(fx.registry)
    registry['tasks'] += list(rows)
    for t in registry['tasks']:
        if t['id'] in rides:
            t['rides'] = rows[0]['id']
    return registry


def two_releases(fx):
    a = release('DS51', 'DL12 release', '10 Oct ~18:00',
                [phase('agents', '17:30', '17:45'), phase('join', '17:45', '17:48'), phase('ci', '17:48', '17:54'),
                 phase('merge', '17:54', '18:00')], {'label': '+1 fix round', 'minutes': 10})
    b = release('DS52', 'Timeline release', '12 Oct', status='To do')
    return with_releases(fx, a, b, rides=('AR6', 'DS6'))


def timeline_of(out):
    return R.find(R.parse_dom(out), 'figure', 'release-timeline')


@test
@with_fixture
def timeline_is_absent_without_open_releases(fx):
    """R5.42: no open release, no figure; a Live release is not open."""
    out = fx.render('full-progress')
    assert timeline_of(out) is None
    registry = with_releases(fx, release('DS51', 'Done release', '09 Oct', status='Live'))
    out = fx.render('full-progress', registry=registry)
    assert timeline_of(out) is None and fx.check(out, 'full-progress', registry=registry) == []
    assert R.release_timeline(registry['tasks'], R._parse_iso(STAMP_ISO), 'Lisbon') == ''
    feature = fx.render('artifacts', registry=two_releases(fx))
    assert timeline_of(feature) is None, 'only Full Progress carries the timeline'


@test
@with_fixture
def release_number_is_shown_once(fx):
    """R5.45: an item that starts with its own RELEASE-<n> does not repeat it in the timeline or the rows."""
    a = release('DS51', 'RELEASE-1: DL12 release', '10 Oct ~18:00')
    b = release('DS52', 'RELEASE-2 · Timeline', '12 Oct', status='To do')
    c = release('DS53', 'RELEASE-3', '13 Oct', status='To do')
    d = release('DS54', 'RELEASE-40 cargo', '14 Oct', status='To do', number=4)
    registry = with_releases(fx, a, b, c, d)
    assert [R.shown_item(t) for t in registry['tasks'][-4:]] == ['DL12 release', 'Timeline', 'RELEASE-3', 'RELEASE-40 cargo']
    out = fx.render('full-progress', registry=registry)
    names = [R.text_of(n, skip=lambda x: x.tag == 'title') for n in R.find_all(timeline_of(out), 'text', 'rt-name')]
    assert names[:2] == ['RELEASE-1 · DL12 release', 'RELEASE-2 · Timeline'], names
    assert '<span class="release-name">RELEASE-1</span>DL12 release' in out and '</span>RELEASE-1: DL12' not in out and '(RELEASE-1: DL12' not in out
    assert fx.check(out, 'full-progress', registry=registry) == []


@test
@with_fixture
def timeline_rows_axis_and_break(fx):
    """R5.42: a row per open release by Expected, riders under the label, a half-hour axis, a day slot after a break."""
    registry = two_releases(fx)
    out = fx.render('full-progress', registry=registry)
    fig = timeline_of(out)
    assert fig is not None and R.text_of(R.find(fig, 'figcaption')) == 'Next releases (Lisbon)'
    names = [R.text_of(n, skip=lambda x: x.tag == 'title') for n in R.find_all(fig, 'text', 'rt-name')]
    assert names == ['RELEASE-1 · DL12 release', 'RELEASE-2 · Timeline rele…'], names
    assert [R.text_of(n, skip=lambda x: x.tag == 'title') for n in R.find_all(fig, 'text', 'rt-sub')] == ['AR6, DS6']
    ticks = [R.text_of(t) for t in R.find_all(R.find(fig, 'g', 'rt-axis'), 'text')]
    assert ticks == ['17:30', '18:00', '18:30', '12 Oct'], ticks
    assert len(R.find_all(fig, 'rect', 'rt-bar')) == 4 and len(R.find_all(fig, 'polygon', 'rt-day')) == 1
    assert R.find(fig, 'path', 'rt-break') is not None
    assert [R.text_of(n) for n in R.find_all(fig, 'text', 'rt-day-label')] == ['12 Oct']
    assert R.text_of(R.find(fig, 'text', 'rt-live-label')) == 'live ~18:00'
    # the figure sits between the status key and the checklist, in section 0
    s0 = R.find(R.parse_dom(out), 'section', pred=lambda n: n.attrs.get('id') == 's0')
    order = list(R.elements(s0))
    fig0 = R.find(s0, 'figure', 'release-timeline')
    assert order.index(R.find(s0, 'p', 'note')) < order.index(fig0) < order.index(R.find(s0, 'table', 'status-checklist'))
    assert fx.check(out, 'full-progress', registry=registry) == []


@test
@with_fixture
def timeline_axis_is_to_scale_from_the_earliest_phase(fx):
    """R5.42: the axis runs from the earliest phase start (or the stamp), floored, to the worst case, ceiled."""
    row = release('DS51', 'Late release', '10 Oct ~15:30', [phase('agents', '14:40', '15:20'), phase('merge', '15:20', '15:30')],
                  {'label': 'slow CI', 'minutes': 25})
    fig = R.release_timeline([row], R._parse_iso(STAMP_ISO), 'Lisbon')
    ticks = [R.text_of(t) for t in R.find_all(R.find(R.parse_dom(fig), 'g', 'rt-axis'), 'text')]
    assert ticks == ['14:30', '15:00', '15:30', '16:00'], ticks
    assert 'slow CI → worst ~15:55' in fig
    long_row = release('DS51', 'Long release', '10 Oct ~21:00', [phase('agents', '13:00', '21:00')])
    ticks = [R.text_of(t) for t in R.find_all(R.find(R.parse_dom(R.release_timeline([long_row], R._parse_iso(STAMP_ISO), 'Lisbon')), 'g', 'rt-axis'), 'text')]
    assert ticks[:3] == ['13:00', '14:00', '15:00'], 'every hour beyond four hours: %s' % ticks


@test
@with_fixture
def timeline_risk_now_and_accessibility(fx):
    """R5.43: the risk extension and worst-case label, the now line at the stamp, role and aria-label, legend."""
    registry = two_releases(fx)
    fig = timeline_of(fx.render('full-progress', registry=registry, stamp_text='10 Oct 17:40', stamp_iso='2026-10-10T17:40+01:00'))
    assert R.text_of(R.find(fig, 'text', 'rt-risk-label')) == '+1 fix round → worst ~18:10'
    assert R.find(fig, 'rect', 'rt-risk') is not None and R.find(fig, 'polygon', 'rt-worst') is not None
    assert R.text_of(R.find(fig, 'text', 'rt-now-label')) == 'now 17:40'
    svg = R.find(fig, 'svg')
    assert svg.attrs['role'] == 'img'
    label = svg.attrs['aria-label']
    assert 'DS51' in label and 'expected live about 18:00, worst case 18:10' in label and 'DS52' in label and 'expected 12 Oct' in label, label
    assert 'min-width' in svg.attrs['style']
    scroll = R.find(fig, 'div', 'timeline-scroll')
    assert R.find(scroll, 'svg') is svg
    legend = R.text_of(R.find(fig, 'p', 'timeline-legend'))
    assert 'agents' in legend and 'join' in legend and 'PR CI' in legend and 'merge + cleanup' in legend
    assert 'Expected (filled diamond) is the sum of the phases' in legend
    # a stamp outside today's axis (12:39 is before the first phase) draws no now line
    assert 'rt-now' not in R.release_timeline(registry['tasks'], R._parse_iso(STAMP_ISO), 'Lisbon')
    late = R.release_timeline(registry['tasks'], R._parse_iso('2026-10-10T22:30+01:00'), 'Lisbon')
    assert 'rt-now' not in late


@test
@with_fixture
def timeline_is_deterministic_and_uses_the_stamp_for_now(fx):
    """R5.42, R7.4: same inputs, same bytes; moving the stamp moves the now line, the wall clock never does."""
    registry = two_releases(fx)
    first = fx.render('full-progress', registry=registry)
    assert first == fx.render('full-progress', registry=registry)
    later = fx.render('full-progress', registry=registry, stamp_text='10 Oct 17:40', stamp_iso='2026-10-10T17:40+01:00')
    assert R.text_of(R.find(timeline_of(later), 'text', 'rt-now-label')) == 'now 17:40'
    assert fx.check(later, 'full-progress', registry=registry) == []


@test
@with_fixture
def timeline_without_phases_is_a_diamond_at_expected(fx):
    """R5.42: a release with no phases is a filled diamond at its Expected only; no bars."""
    registry = with_releases(fx, release('DS51', 'Plain release', '10 Oct ~16:00'))
    fig = timeline_of(fx.render('full-progress', registry=registry))
    assert R.find(fig, 'rect', 'rt-bar') is None and R.find(fig, 'polygon', 'rt-expected') is not None
    assert R.text_of(R.find(fig, 'text', 'rt-live-label')) == 'live ~16:00'


@test
@with_fixture
def check_finds_a_wrong_timeline(fx):
    """R5.42, R5.43: a missing, extra, unlabelled or misplaced timeline is reported."""
    registry = two_releases(fx)
    out = fx.render('full-progress', registry=registry)
    import re
    gone = re.sub(r'<figure class="release-timeline">.*?</figure>\n?', '', out, flags=re.S)
    assert 'R5.42' in reqs(fx.check(gone, 'full-progress', registry=registry))
    plain = fx.render('full-progress')
    extra = plain.replace('<div class="table-scroll"><table class="status-checklist">',
                 '<figure class="release-timeline"><figcaption>Next releases (Lisbon)</figcaption></figure>\n<div class="table-scroll"><table class="status-checklist">')
    assert 'R5.42' in reqs(fx.check(extra, 'full-progress'))
    bad = sub1(out, 'role="img"', 'role="presentation"')
    assert 'R5.43' in reqs(fx.check(bad, 'full-progress', registry=registry))
    bad = sub1(out, '<figcaption>Next releases (Lisbon)</figcaption>', '<figcaption>Next releases</figcaption>')
    assert 'R5.42' in reqs(fx.check(bad, 'full-progress', registry=registry))


@test
@with_fixture
def timeline_crosses_midnight(fx):
    """R5.42a: a release due just after midnight keeps its bars and diamond on an axis that crosses midnight."""
    def ph(name, a, b):
        return {'name': name, 'start': a, 'end': b}
    row = release('DS51', 'Midnight release', '12 Oct ~00:05',
                  [ph('agents', '2026-10-11T23:40+01:00', '2026-10-11T23:51+01:00'), ph('join', '2026-10-11T23:51+01:00', '2026-10-11T23:56+01:00'),
                   ph('ci', '2026-10-11T23:56+01:00', '2026-10-12T00:00+01:00'), ph('merge', '2026-10-12T00:00+01:00', '2026-10-12T00:05+01:00')],
                  {'label': '+1 fix round', 'minutes': 10})
    stamp = '2026-10-11T23:57+01:00'
    out = R.release_timeline([row], R._parse_iso(stamp), 'Lisbon')
    fig = R.parse_dom(out)
    assert len(R.find_all(fig, 'rect', 'rt-bar')) == 4 and R.find(fig, 'polygon', 'rt-expected') is not None
    assert R.find(fig, 'polygon', 'rt-day') is None
    ticks = [R.text_of(t) for t in R.find_all(R.find(fig, 'g', 'rt-axis'), 'text')]
    assert ticks[:3] == ['23:30', '12 Oct 00:00', '12 Oct 00:30'], ticks
    assert R.text_of(R.find(fig, 'text', 'rt-now-label')) == 'now 23:57'
    assert R.text_of(R.find(fig, 'text', 'rt-live-label')) == 'live ~00:05'
    # the whole artifact checks clean, and a release more than 24 hours away still takes a day slot
    registry = with_releases(fx, row, release('DS52', 'Far release', '14 Oct ~09:00'))
    kw = dict(registry=registry, stamp_text='11 Oct 23:57', stamp_iso=stamp)
    html = fx.render('full-progress', **kw)
    assert len(R.find_all(timeline_of(html), 'polygon', 'rt-day')) == 1
    assert fx.check(html, 'full-progress', **kw) == []


@test
@with_fixture
def check_finds_a_timed_release_in_a_day_slot(fx):
    """R5.42a: a timed release within 24 hours drawn as a day slot is reported."""
    registry = with_releases(fx, release('DS51', 'Soon release', '10 Oct ~16:00'))
    out = fx.render('full-progress', registry=registry)
    assert 'R5.42a' not in reqs(fx.check(out, 'full-progress', registry=registry))
    bad = sub1(out, 'class="rt-expected"', 'class="rt-day"')
    assert 'R5.42a' in reqs(fx.check(bad, 'full-progress', registry=registry))


@test
def timeline_css_uses_tokens():
    """R5.43: the timeline styles use design tokens and no literal colour; the bars use the four phase tokens."""
    import re
    css = R.structure_css(PLUGIN)
    block = css[css.index('/* Release timeline'):]
    assert not re.search(r'#[0-9a-fA-F]{3,6}\b|rgb\(|hsl\(', block), 'colours must be tokens'
    for cls, token in (('agents', '--running-mark'), ('join', '--signal'), ('ci', '--live'), ('merge', '--ink')):
        assert re.search(r'\.rt-bar\.%s \{ fill: var\(%s\)' % (cls, token), block), cls
        assert re.search(r'\.rt-swatch\.%s \{ background: var\(%s\)' % (cls, token), block), cls
    assert 'var(--failed)' in block and 'var(--rule-strong)' in block and 'overflow-x: auto' in block


@test
@with_fixture
def timeline_is_never_scaled_up(fx):
    """R5.43: one release with no phases and a day Expected is drawn at the design width, never scaled up."""
    import re
    registry = with_releases(fx, release('DS52', 'Timeline release', '12 Oct', status='To do'))
    fig = R.release_timeline(registry['tasks'], R._parse_iso(STAMP_ISO), 'Lisbon')
    match = re.search(r'viewBox="0 0 (\d+) (\d+)".*?style="min-width:(\d+)px;max-width:(\d+)px"', fig)
    assert match, fig[:300]
    width, height, low, high = (int(x) for x in match.groups())
    assert width == R.TL_WIDTH == 960 and high == width and low <= high and height < 200, match.groups()
    out = fx.render('full-progress', registry=registry)
    assert fx.check(out, 'full-progress', registry=registry) == []


def no_release_task(tid, item, expected, status='Running', basis='', started=None):
    row = task(tid, 'project', status, item, expected, '2026-10-10T12:00+01:00', 'luismc-artifacts')
    row['no_release'] = 'catalogue check'
    if basis:
        row['expected_basis'] = basis
    if started:
        row['started'] = started
    return row


@test
@with_fixture
def other_work_strip_renders_beside_the_release_rows(fx):
    """R5.42b: one release and two no-release tasks draw both strips; Built or Live no-release tasks are left out."""
    registry = with_releases(fx, release('DS51', 'DL12 release', '10 Oct ~18:00',
                                         [phase('agents', '17:30', '18:00')]),
                             no_release_task('DS60', 'Catalogue check', '10 Oct ~16:00', basis='scan 40 min', started='2026-10-10T14:00+01:00'),
                             no_release_task('DS61', 'Study of covers', '11 Oct', status='To do'),
                             no_release_task('DS62', 'Old publish', '09 Oct', status='Live'),
                             no_release_task('DS63', 'Done check', '10 Oct ~15:00', status='Built'))
    out = fx.render('full-progress', registry=registry)
    fig = timeline_of(out)
    assert fig is not None
    assert R.text_of(R.find(fig, 'text', 'rt-strip-title')) == 'Other work (no release)'
    names = [R.text_of(n, skip=lambda x: x.tag == 'title') for n in R.find_all(fig, 'text', 'rt-name')]
    assert names == ['RELEASE-1 · DL12 release', 'DS60 · Catalogue check', 'DS61 · Study of covers'], names
    bars = R.find_all(fig, 'rect', 'rt-other')
    assert len(bars) == 1 and 'status-running' in bars[0].attrs['class'], bars
    assert 'scan 40 min' in R.text_of(R.find(fig, 'text', 'rt-other-label'))
    assert 'DS62' not in str(fig.attrs) and 'Old publish' not in out.split('Other work')[1].split('</figure>')[0]
    assert 'Done check' not in out.split('Other work')[1].split('</figure>')[0]
    assert fx.check(out, 'full-progress', registry=registry) == []


@test
@with_fixture
def other_work_strip_alone_and_overdue(fx):
    """R5.42b: with no open release the strip still draws; a task past its Expected is outlined as overdue."""
    registry = copy.deepcopy(fx.registry)
    registry['tasks'].append(no_release_task('DS60', 'Late check', '10 Oct ~11:00', status='Waiting'))
    out = fx.render('full-progress', registry=registry)
    fig = timeline_of(out)
    assert fig is not None and 'overdue' in R.find(fig, 'rect', 'rt-other').attrs['class']
    assert fx.check(out, 'full-progress', registry=registry) == []
    plain = copy.deepcopy(fx.registry)
    plain['tasks'].append(no_release_task('DS60', 'Live check', '10 Oct ~11:00', status='Live'))
    assert timeline_of(fx.render('full-progress', registry=plain)) is None


@test
@with_fixture
def tiles_say_tasks(fx):
    """R5.8a: a tile reads `tasks live` and, for one, `task running`."""
    out = fx.render('full-progress')
    assert '<div class="count">4</div><div class="label">tasks live</div>' in out
    assert '<div class="count">1</div><div class="label">task waiting</div>' in out


@test
@with_fixture
def full_progress_groups_by_release(fx):
    """R5.46: a group per open release (release row, then its riders), then Not in a release yet, then the others."""
    registry = two_releases(fx)
    out = fx.render('full-progress', registry=registry)
    rows = table_rows(out)
    groups = [r for r in rows if r[0] == 'group']
    assert [g[1] for g in groups] == ['release-1', 'release-2', 'now', 'you', 'built'], groups
    assert [g[2] for g in groups][:2] == ['RELEASE-1 · live ~18:00 · worst ~18:10', 'RELEASE-2 · live 12 Oct'], groups
    assert [g[2] for g in groups][2] == 'Not in a release yet'
    first = [r[1] for r in rows[:rows.index(groups[1])] if r[0] == 'task']
    assert first == ['DS51', 'AR6', 'DS6'], first                  # the release, then its riders (ties by ID)
    # a task appears in exactly one group
    ids = [r[1] for r in rows if r[0] == 'task'] + [r[1] for r in table_rows(out, 1) if r[0] == 'task']
    assert len(ids) == len(set(ids)) == len(registry['tasks'])
    assert 'AR6' not in [r[1] for r in rows[rows.index(groups[2]):] if r[0] == 'task']
    assert fx.check(out, 'full-progress', registry=registry) == []
    # a feature artifact keeps the groups of R6.2
    feature = table_rows(fx.render('artifacts', registry=registry))
    assert [r[1] for r in feature if r[0] == 'group'] == ['now', 'built'], feature


@test
@with_fixture
def release_group_heading_with_risk(fx):
    """R5.46: ` · worst ~HH:MM` only when the release has a risk; a release row starts with its RELEASE-n name."""
    registry = two_releases(fx)
    out = fx.render('full-progress', registry=registry)
    assert '<strong>RELEASE-1 · live ~18:00 · worst ~18:10</strong>' in out
    assert '<strong>RELEASE-2 · live 12 Oct</strong>' in out and 'RELEASE-2 · live 12 Oct · worst' not in out
    assert '<span class="task-id">DS51</span><span class="release-name">RELEASE-1</span>DL12 release' in out
    assert '<li data-glance-task="DS51"><span class="task-id">DS51</span><span class="release-name">RELEASE-1</span>' in out
    # a timed release without a risk: live time only
    registry = with_releases(fx, release('DS51', 'Plain', '10 Oct ~19:00', status='Running'))
    assert '<strong>RELEASE-1 · live ~19:00</strong>' in fx.render('full-progress', registry=registry)


@test
@with_fixture
def rows_show_the_release_they_rode(fx):
    """R5.46: Live or built rows (and a feature artifact's rows) that ride a release show it in a muted line."""
    registry = two_releases(fx)
    registry['tasks'].append(release('DS53', 'Shipped', '09 Oct', status='Live'))
    for t in registry['tasks']:
        if t['id'] in ('AR5', 'MP1'):
            t['rides'] = 'DS53'
    out = fx.render('full-progress', registry=registry)
    for tid, name in (('AR5', 'RELEASE-3'), ('MP1', 'RELEASE-3')):
        row = out[out.index('<tr data-task="%s">' % tid):]
        row = row[:row.index('</tr>')]
        assert '<span class="release-line"><span class="release-name">%s</span></span>' % name in row, row
    feature = fx.render('artifacts', registry=registry)
    ar6 = feature[feature.index('<tr data-task="AR6">'):]
    assert '<span class="release-line"><span class="release-name">RELEASE-1</span></span>' in ar6[:ar6.index('</tr>')]
    assert fx.check(out, 'full-progress', registry=registry) == []
    assert fx.check(feature, 'artifacts', registry=registry) == []


@test
@with_fixture
def no_release_line_in_full_progress(fx):
    """R5.47a: a task that ships nothing sits in Not in a release yet with a muted `ships nothing: <reason>` line;
    check reports a missing or wrong line."""
    registry = two_releases(fx)
    for t in registry['tasks']:
        if t['id'] == 'AR5':
            t['status'], t['expected'] = 'Running', '10 Oct ~18:30'
            t['no_release'] = 'a publish, nothing to ship'
            t.pop('rides', None)
    out = fx.render('full-progress', registry=registry)
    row = out[out.index('<tr data-task="AR5">'):]
    row = row[:row.index('</tr>')]
    assert '<span class="no-release-line">ships nothing: a publish, nothing to ship</span>' in row, row
    assert 'release-line' not in row.replace('no-release-line', '')
    before = out[:out.index('<tr data-task="AR5">')]
    assert before.rindex('data-group="') > 0 and 'data-group="now"' in before[before.rindex('<details class="status-fold'):]
    assert 'Not in a release yet' in before
    assert 'no-release-line' in fx.render('artifacts', registry=registry)
    assert fx.check(out, 'full-progress', registry=registry) == []
    expect(fx, sub1(out, '<span class="no-release-line">ships nothing: a publish, nothing to ship</span>', ''),
           'full-progress', ['R5.47a'], registry=registry)
    expect(fx, sub1(out, 'ships nothing: a publish', 'ships nothing: a study'), 'full-progress', ['R5.47a'], registry=registry)


@test
@with_fixture
def check_finds_a_row_in_the_wrong_release_group(fx):
    """R5.46, R5.45: a rider outside its release group, a wrong heading, a missing release line or name are findings."""
    registry = two_releases(fx)
    registry['tasks'].append(release('DS53', 'Shipped', '09 Oct', status='Live'))
    for t in registry['tasks']:
        if t['id'] == 'AR5':
            t['rides'] = 'DS53'
    out = fx.render('full-progress', registry=registry)
    expect(fx, move_row(out, 'AR6', 'data-group="release-2"'), 'full-progress', ['R5.46'], registry=registry)
    expect(fx, sub1(out, 'RELEASE-1 · live ~18:00 · worst ~18:10', 'RELEASE-1 · live ~18:00'), 'full-progress', ['R5.46'], registry=registry)
    expect(fx, sub1(out, '<span class="release-line"><span class="release-name">RELEASE-3</span></span>', ''), 'full-progress', ['R5.46'], registry=registry)
    expect(fx, sub1(out, '<span class="task-id">DS52</span><span class="release-name">RELEASE-2</span>', '<span class="task-id">DS52</span>'),
           'full-progress', ['R5.45'], registry=registry)


@test
@with_fixture
def state_column_counts(fx):
    """R5.44: Complete for a finished feature, else a chip per open status in order, then open decisions."""
    out = fx.render('full-progress')
    rows = _s1_rows(out)
    assert rows[0][3] == '1 Running2 Built1 To do' and rows[1][3] == '1 Running', rows
    dom = R.parse_dom(out)
    chips = [(R.text_of(c), c.attrs['class']) for c in R.find_all(R.find(dom, 'table', 'feature-list'), 'span', 'status-chip')]
    assert ('1 Running', 'status-chip status-running') in chips and ('2 Built', 'status-chip status-built') in chips
    done = copy.deepcopy(fx.registry)
    for t in done['tasks']:
        if t['owner'] == 'models':
            t['status'], t['expected'] = 'Live', '09 Oct'
    out = fx.render('full-progress', registry=done)
    assert _s1_rows(out)[1][3] == 'Complete'
    assert R.find(_feature_fold(out, 'complete'), 'span', 'status-live') is not None
    assert fx.check(out, 'full-progress', registry=done) == []
    assert R.state_chips([task('X1', 'k', 'Needs you', 'i', '10 Oct'), task('X2', 'k', 'Failed', 'i', ''), task('X3', 'k', 'On hold', 'i', '10 Oct'),
                          task('X4', 'k', 'Waiting', 'i', '10 Oct')], [{'id': 'D1', 'status': 'open'}, {'id': 'D2', 'status': 'open'}]) == [
        ('status-needs-you', '1 Needs you'), ('status-failed', '1 Failed'), ('status-waiting', '1 Waiting'),
        ('status-on-hold', '1 On hold'), ('status-needs-you', '2 open decisions')]


@test
@with_fixture
def check_state_column(fx):
    """R5.44: a State that differs from the registry is reported."""
    out = fx.render('full-progress')
    bad = sub1(out, '1 Running</span><span class="status-chip status-built">2 Built', '3 Running</span><span class="status-chip status-built">2 Built')
    assert 'R5.44' in reqs(fx.check(bad, 'full-progress'))


@test
@with_fixture
def other_work_bar_starts_at_started(fx):
    """R5.48: an open no-release task's bar starts at its `started`, not at now (12:39); without one it starts at now,
    and the bar is drawn wider (the axis begins at the start)."""
    ref = R._parse_iso(STAMP_ISO)
    widths = {}
    for started in ('2026-10-10T09:00+01:00', None):
        row = no_release_task('DS60', 'Catalogue check', '10 Oct ~16:00', status='Waiting', started=started)
        facts = R._other_row(row, ref)
        assert facts['start_min'] == (540 if started else 12 * 60 + 39), facts
        registry = with_releases(fx, row)
        out = fx.render('full-progress', registry=registry)
        assert fx.check(out, 'full-progress', registry=registry) == []
        bar = R.find_all(timeline_of(out), 'rect', 'rt-other')[0]
        widths[started] = float(bar.attrs['width'])
    assert widths['2026-10-10T09:00+01:00'] > widths[None], widths


@test
@with_fixture
def dropped_release_is_closed_history(fx):
    """R5.49: a Dropped release is not open: no bar on the timeline, not in open_releases, listed under Live or built
    with `dropped: folded into RELEASE-2`, a ninth chip and tile; check is clean."""
    kept = release('DS52', 'Kept release', '10 Oct ~18:00', [phase('agents', '17:30', '18:00')])
    gone = release('DS51', 'Folded release', '10 Oct ~17:00', [phase('agents', '16:30', '17:00')], status='Dropped')
    gone['dropped_into'] = 'DS52'
    registry = with_releases(fx, gone, kept)
    assert [t['id'] for t in R.open_releases(registry['tasks'])] == ['DS52']
    out = fx.render('full-progress', registry=registry)
    fig = timeline_of(out)
    names = [R.text_of(n, skip=lambda x: x.tag == 'title') for n in R.find_all(fig, 'text', 'rt-name')]
    assert names == ['RELEASE-2 · Kept release'], names
    row = out[out.index('<tr data-task="DS51">'):]
    row = row[:row.index('</tr>')]
    assert '<span class="dropped-line">dropped: folded into RELEASE-2</span>' in row and 'status-dropped' in row, row
    assert R.dropped_line(gone, {'DS52': kept}) == 'dropped: folded into RELEASE-2'
    assert 'status-count-tile status-dropped' in out and 'status-chip status-dropped' in out
    assert R.find([f for f in R.find_all(R.parse_dom(out), 'details', 'status-fold') if not R.has_class(f, 'feature-group')][-1], 'tr') is not None
    assert fx.check(out, 'full-progress', registry=registry) == []
    bad = out.replace('dropped: folded into RELEASE-2', 'dropped: something else')
    assert 'R5.49' in reqs(fx.check(bad, 'full-progress', registry=registry))


@test
@with_fixture
def narrow_width_css_and_labels(fx):
    """CO669: a task row stacks into a card in a narrow box, every cell carries its label, and the contents nav wraps."""
    css = R.structure_css()
    assert '@container (max-width: 46rem)' in css and '@media (max-width: 56rem)' in css
    assert 'attr(data-label)' in css and 'content: "Rides "' in css
    assert re.search(r'nav\.contents \.contents-links[^{]*\{[^}]*flex-wrap: wrap', css), 'the nav wraps'
    assert 'overflow-wrap: anywhere' in css and 'min-width: 0' in css
    assert '.timeline-scroll' in css and 'container-type: inline-size' in css
    for kind in ('full-progress', 'artifacts'):
        out = fx.render(kind)
        for label in ('Status', 'Item', 'Detail', 'Expected'):
            assert 'data-label="%s"' % label in out, (kind, label)
    fp = fx.render('full-progress')
    assert 'data-label="App / service"' in fp and 'data-label="State"' in fp
    for label in ('Feature artifact', 'Last updated', 'Tasks', 'Where it stands'):
        assert 'data-label="%s"' % label in fp, label


@test
@with_fixture
def contents_rail_toggle(fx):
    """CO669: both page kinds carry the Hide / Show contents button (aria-expanded) and a storage-safe script."""
    for kind in ('full-progress', 'artifacts'):
        out = fx.render(kind)
        button = R.find(R.parse_dom(out), 'button', pred=lambda n: n.attrs.get('id') == 'contents-toggle')
        assert button is not None, kind
        assert button.attrs.get('aria-expanded') == 'true' and button.attrs.get('aria-controls') == 'contents-links'
        assert 'Hide contents' in R.text_of(button) and 'Show contents' in out
        assert "localStorage.setItem('contents-rail'" in out and "localStorage.getItem('contents-rail')" in out
        assert re.search(r"try \{ remembered = window\.localStorage\.getItem[^}]*\} catch", out), 'reads are guarded'
        assert 'data-contents' in out
        assert R.find(R.parse_dom(out), 'div', pred=lambda n: n.attrs.get('id') == 'contents-links') is not None
    assert '.layout[data-contents="collapsed"]' in R.structure_css()


def main() -> int:
    passed, failed = 0, 0
    names = sys.argv[1:]            # named cases: run the tests whose name contains one of them
    for fn in TESTS:
        if names and not any(n in fn.__name__ for n in names):
            continue
        try:
            fn()
        except Exception:  # noqa: BLE001
            failed += 1
            print('FAIL', fn.__name__)
            print('     ' + traceback.format_exc().strip().replace('\n', '\n     ')[-1800:])
        else:
            passed += 1
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
