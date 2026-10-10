#!/usr/bin/env python3
"""Tests for claude/plugins/artifacts/scripts/render_artifacts.py (ARTIFACTSPEC 1.0.0, sections 4 to 6 and 14).

Every check of check_html gets a fixture that breaks exactly that rule and must produce exactly that
requirement ID; the clean fixtures must produce nothing. A check nobody has seen fire is not a check.

Run:  python -I tools/test_render_artifacts.py     (prints "N passed, 0 failed")
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'claude', 'plugins', 'artifacts')
sys.path.insert(0, os.path.join(PLUGIN, 'scripts'))

import render_artifacts as R  # noqa: E402

STAMP_TEXT, STAMP_ISO = '10 Oct 12:39', '2026-10-10T12:39+01:00'
FP_URL, AR_URL = 'https://claude.ai/artifact/fp-url', 'https://claude.ai/artifact/ar-url'


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
            {'key': 'artifacts', 'title': 'Feature: Project artifacts standard', 'url': AR_URL,
             'file': 'feature-project-artifacts-standard.html', 'prefix': 'AR', 'apps': ['luismc-artifacts'], 'published_sha256': ''},
            {'key': 'models', 'title': 'Feature: Model and effort profiles', 'url': '',
             'file': 'feature-model-and-effort-profiles.html', 'prefix': 'MP', 'apps': ['luismc-project-setup'], 'published_sha256': ''},
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
                                 self.record, kw.get('stamp_text', STAMP_TEXT), kw.get('stamp_iso', STAMP_ISO))

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
def render_is_a_fragment_beginning_with_title(fx):
    for key in ('full-progress', 'artifacts'):
        out = fx.render(key)
        assert out.startswith('<title>'), out[:40]
        for tag in ('<html', '<head>', '<body', '{{', '}}'):
            assert tag not in out, tag
        assert out.endswith('\n')


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
    assert cells == [['Feature: Project artifacts standard', 'AR5 to AR16', 'The design is agreed.'],
                     ['Feature: Model and effort profiles', 'MP1 to MP2, DS2', 'Effort question is live!']], cells
    anchors = [a.attrs['href'] for a in R.find_all(s1node, 'a')]
    assert anchors == [AR_URL], anchors  # the feature without a URL is listed unlinked


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
    dom = R.parse_dom(html)
    table = R.find_all(dom, 'table', 'status-checklist')[which]
    out = []
    for tr in R.find_all(table, 'tr'):
        if R.has_class(tr, 'status-group'):
            out.append(('group', tr.attrs['data-group'], R.text_of(tr)))
        elif 'data-task' in tr.attrs:
            out.append(('task', tr.attrs['data-task']))
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
        ('group', 'now', 'Running now and next'),
        ('task', 'DS6'), ('task', 'DS7'), ('task', 'AR6'),      # 10 Oct ~13:45 (twice, registry order), then 10 Oct ~15:30
        ('task', 'AR7'), ('task', 'DS8'), ('task', 'MP2'),      # 11 Oct, 12 Oct, 13 Oct
        ('group', 'you', 'Needs you, failed or on hold'),
        ('task', 'DS9'), ('task', 'DS11'), ('task', 'DS10'),    # Needs you, Failed, On hold
        ('group', 'built', 'Live or built'),
        ('task', 'AR5'), ('task', 'MP1'), ('task', 'DS2'), ('task', 'DS3'),   # newest changed first
    ], rows


@test
@with_fixture
def earlier_fold_older_than_14_days(fx):
    out = fx.render('full-progress')
    assert table_rows(out, 1) == [('task', 'DS1'), ('task', 'AR16')], table_rows(out, 1)  # 24 Sep, 20 Sep: newest first
    dom = R.parse_dom(out)
    details = R.find_all(dom, 'details')
    assert len(details) == 1 and 'open' not in details[0].attrs and R.text_of(R.find(details[0], 'summary')) == 'Earlier'
    assert '<details' not in fx.render('artifacts')  # a feature artifact never folds


@test
@with_fixture
def earlier_fold_boundary_is_14_days_from_the_stamp(fx):
    # stamp 10 Oct 12:39; a change at exactly 26 Sep 12:39 is 14 days old: not older, so it stays shown
    fx.registry['tasks'][4]['changed'] = '2026-09-26T12:39+01:00'          # DS1: exactly 14 days
    fx.registry['tasks'][3]['changed'] = '2026-09-26T12:38+01:00'          # AR16: one minute older
    out = fx.render('full-progress')
    assert table_rows(out, 1) == [('task', 'AR16')], table_rows(out, 1)
    assert ('task', 'DS1') in table_rows(out, 0)
    assert fx.check(out, 'full-progress') == []


@test
@with_fixture
def earlier_fold_follows_the_stamp_not_the_clock(fx):
    out = fx.render('full-progress', stamp_text='01 Oct 09:00', stamp_iso='2026-10-01T09:00+01:00')
    assert '<details' not in out  # everything is within 14 days of 1 Oct except AR16 (11 days) - all shown
    assert ('task', 'AR16') in table_rows(out, 0)


@test
@with_fixture
def a_group_with_only_folded_rows_is_still_closed_correctly(fx):
    fx.registry['tasks'] = [t for t in fx.registry['tasks'] if t['status'] not in ('Live', 'Built') or t['id'] in ('AR16', 'DS1')]
    out = fx.render('full-progress')
    rows = table_rows(out, 0)
    assert ('group', 'built', 'Live or built') not in rows, rows
    assert table_rows(out, 1) == [('task', 'DS1'), ('task', 'AR16')]
    assert fx.check(out, 'full-progress') == []


@test
@with_fixture
def needs_you_sentence(fx):
    out = fx.render('full-progress')
    lede = R.text_of(R.find(R.parse_dom(out), 'p', 'lede'))
    assert lede == ('All ongoing work in dev-standards. More words follow. '
                    'Needs you: DS9 Sign off the <rules> & ship; DS11 Release CI.'), lede
    # a feature artifact lists only its own tasks, and says so when there are none
    assert R.text_of(R.find(R.parse_dom(fx.render('artifacts')), 'p', 'lede')).endswith('Nothing needs you.')
    fx.registry['tasks'][0]['status'] = 'Needs you'
    fx.registry['tasks'][0]['expected'] = '12 Oct'
    assert R.text_of(R.find(R.parse_dom(fx.render('artifacts')), 'p', 'lede')).endswith('Needs you: AR5 ARTIFACTSPEC 1.0.0.')


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
    assert tiles == [('live', '4', 'status-count-tile status-live'), ('built', '2', 'status-count-tile status-built'),
                     ('running', '3', 'status-count-tile status-running'),
                     ('needs you', '1', 'status-count-tile status-needs-you'), ('waiting', '1', 'status-count-tile status-waiting'),
                     ('to do', '2', 'status-count-tile status-to-do'), ('on hold', '1', 'status-count-tile status-on-hold'),
                     ('failed', '1', 'status-count-tile status-failed')], tiles
    feature = R.parse_dom(fx.render('artifacts'))
    got = [(R.text_of(R.find(t, 'div', 'label')), R.text_of(R.find(t, 'div', 'count'))) for t in R.find_all(feature, 'div', 'status-count-tile')]
    assert got == [('built', '2'), ('running', '1'), ('to do', '1')], got


@test
@with_fixture
def links_on_the_full_progress_artifact(fx):
    dom = R.parse_dom(fx.render('full-progress'))
    table = R.find(dom, 'table', 'status-checklist')
    hrefs = {tr.attrs['data-task']: (R.find(tr, 'a').attrs['href'] if R.find(tr, 'a') else None)
             for tr in R.find_all(table, 'tr', pred=lambda n: 'data-task' in n.attrs)}
    assert hrefs['AR6'] == AR_URL and hrefs['AR5'] == AR_URL
    assert hrefs['DS6'] is None and hrefs['MP1'] is None  # project task; feature without a URL


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
    expect(fx, sub1(out, '<th>Detail</th>', ''), 'artifacts', ['R6.4'])
    expect(fx, sub1(out, 'Expected (Lisbon)', 'Expected'), 'artifacts', ['R6.4'])
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, '<th>App / service</th>', '', count=2), 'full-progress', ['R6.4'])
    # a feature artifact must not carry the App / service column
    expect(fx, sub1(out, '<th>Detail</th>', '<th>App / service</th><th>Detail</th>'), 'artifacts', ['R6.4'])
    expect(fx, sub1(out, '<td colspan="4"><strong>Live or built', '<td colspan="5"><strong>Live or built'), 'artifacts', ['R6.4'])


@test
@with_fixture
def check_r61_statuses(fx):
    out = fx.render('artifacts')
    expect(fx, sub1(out, '<tr data-task="AR6"><td><span class="status-chip status-running">', '<tr data-task="AR6"><td><span class="status-chip status-live">'),
           'artifacts', ['R6.1'])
    got = fx.check(sub1(out, '<span class="status-chip status-running">Running</span></td><td><span class="task-id">AR6',
                        '<span class="status-chip status-merged">Merged</span></td><td><span class="task-id">AR6'), 'artifacts')
    assert 'R6.1' in reqs(got), got


def move_row(html, task_id, after_marker):
    start = html.index('<tr data-task="%s">' % task_id)
    end = html.index('</tr>', start) + 5
    row = html[start:end]
    html = html[:start] + html[end + 1:]
    at = html.index(after_marker)
    at = html.index('</tr>', at) + 5
    return html[:at] + '\n' + row + html[at:]


@test
@with_fixture
def check_r62_groups(fx):
    fp = fx.render('full-progress')
    # a Running row placed under the "Needs you, failed or on hold" group
    expect(fx, move_row(fp, 'DS6', 'data-group="you"'), 'full-progress', ['R6.2'])
    # group heading text and order
    expect(fx, sub1(fp, '<strong>Running now and next</strong>', '<strong>Running next</strong>'), 'full-progress', ['R6.2'])
    # order inside a group: AR7 (11 Oct) moved before DS6 (10 Oct)
    expect(fx, move_row(fp, 'AR7', 'data-group="now"'), 'full-progress', ['R6.2'])
    # two groups swapped
    a, b = fp.index('<tr class="status-group" data-group="now">'), fp.index('<tr class="status-group" data-group="you">')
    c = fp.index('<tr class="status-group" data-group="built">')
    swapped = fp[:a] + fp[b:c] + fp[a:b] + fp[c:]
    expect(fx, swapped, 'full-progress', ['R6.2'])
    # Live or built not newest first
    out = fx.render('artifacts')
    expect(fx, move_row(out, 'AR16', 'data-group="built"'), 'artifacts', ['R6.2'])


@test
@with_fixture
def check_r63_earlier_fold(fx):
    fp = fx.render('full-progress')
    # un-fold: take the details out
    start = fp.index('<details class="earlier">')
    end = fp.index('</details>') + len('</details>')
    expect(fx, fp[:start] + fp[end:], 'full-progress', ['INV-1', 'R6.3', 'R6.5'])    # rows lost entirely: also not in the checklist
    expect(fx, sub1(fp, '<details class="earlier">', '<details class="earlier" open>'), 'full-progress', ['R6.3'])
    expect(fx, sub1(fp, '<summary>Earlier</summary>', '<summary>Older</summary>'), 'full-progress', ['R6.3'])
    # a registry whose change dates disagree with the fold
    registry = copy.deepcopy(fx.registry)
    registry['tasks'][5]['changed'] = '2026-08-01T10:00+01:00'                         # DS2 is old, but shown
    got = fx.check(sub1(fp, '<script type="application/json" id="task-registry">', '<script type="application/json" id="task-registry">'), 'full-progress', registry=registry)
    assert 'R6.3' in reqs(got), got
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
    expect(fx, sub1(out, '<div class="count">2</div><div class="label">built</div>', '<div class="count">3</div><div class="label">built</div>'),
           'artifacts', ['R5.8'])
    expect(fx, sub1(out, '<div class="status-count-tile status-running"><div class="count">1</div><div class="label">running</div></div>', ''),
           'artifacts', ['R5.8'])
    expect(fx, sub1(out, '<div class="label">built</div>', '<div class="label">live</div>'), 'artifacts', ['R5.8'])
    expect(fx, sub1(out, '</div></div>\n<p class="note">Key', '</div><div class="status-count-tile status-failed"><div class="count">0</div><div class="label">failed</div></div></div>\n<p class="note">Key'),
           'artifacts', ['R5.8'])


@test
@with_fixture
def check_r65_feature_tasks_linked_on_full_progress(fx):
    fp = fx.render('full-progress')
    linked = '<a href="%s"><span class="task-id">AR6</span>Templates</a>' % AR_URL
    assert linked in fp
    expect(fx, sub1(fp, linked, '<span class="task-id">AR6</span>Templates'), 'full-progress', ['R6.5'])
    expect(fx, sub1(fp, linked, '<a href="https://claude.ai/artifact/other"><span class="task-id">AR6</span>Templates</a>'), 'full-progress', ['R6.5'])
    start = fp.index('<tr data-task="AR6">')
    end = fp.index('</tr>', start) + 6
    expect(fx, fp[:start] + fp[end:], 'full-progress', ['INV-1', 'R6.5'])


@test
@with_fixture
def check_r56_feature_list(fx):
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, '<a href="%s">Feature: Project artifacts standard</a>' % AR_URL, 'Feature: Project artifacts standard'), 'full-progress', ['R5.6'])
    expect(fx, sub1(fp, '<td>Feature: Model and effort profiles</td>', '<td>Feature: Model and effort</td>'), 'full-progress', ['R5.6'])


@test
@with_fixture
def check_r57_lede(fx):
    fp = fx.render('full-progress')
    expect(fx, sub1(fp, 'Needs you: DS9 Sign off the &lt;rules&gt; &amp; ship; DS11 Release CI.', 'Nothing needs you.'), 'full-progress', ['R5.7'])
    out = fx.render('artifacts')
    expect(fx, sub1(out, 'Nothing needs you.', 'Needs you: AR6 Templates.'), 'artifacts', ['R5.7'])


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
    assert set(content) == {'meta', 'sections', 'history'}
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
    assert R.STATUSES == ('Live', 'Built', 'Running', 'Needs you', 'Waiting', 'To do', 'On hold', 'Failed')
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
    known = {'title', 'fonts_link', 'design_css', 'structure_css', 'extra_css', 'kind_label', 'project', 'hero', 'contents',
             'sections', 'stamp', 'lede', 'tiles', 'key', 'checklist', 'registry'}
    for name in ('feature-artifact.html', 'full-progress-artifact.html'):
        text = open(os.path.join(PLUGIN, 'templates', name), encoding='utf-8').read()
        found = set(re.findall(r'\{\{(\w+)\}\}', text))
        assert found <= known, found - known
        assert text.startswith('<title>{{title}}</title>')
        assert ('{{registry}}' in text) == (name.startswith('full-progress'))
        assert text.count('<script') == 1 or (name.startswith('full') and text.count('<script') == 1)


def main() -> int:
    passed, failed = 0, 0
    for fn in TESTS:
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
