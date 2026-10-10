#!/usr/bin/env python3
"""Prove project_artifacts.py does what ARTIFACTSPEC 1.0.0 section 7 says (R13.1).

Every case builds throwaway git repositories with a local bare remote and runs
the real command line against them. Nothing here pushes to any real remote.

Two groups run the same cases:
  fake  a small stand-in for render_artifacts.py, written into a temp copy of
        the plugin, so this file proves the script on its own;
  real  the plugin's own render_artifacts.py; skipped, with a message, while
        that module is not importable.

Run:  python -I tools/test_project_artifacts.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_PLUGIN = ROOT / 'claude' / 'plugins' / 'artifacts'
NOW = '2026-10-10T11:39:00+00:00'

FAKE_RENDER = r'''
"""A stand-in renderer with the exact API the script expects (tests only)."""
import html as _h
import json
import re
from pathlib import Path

STATUSES = ['Live', 'Done', 'Running', 'Needs you', 'Waiting', 'To do', 'On hold', 'Failed']
REQUIRED_TOKENS = ['--paper', '--ink']


class ContentError(Exception):
    def __init__(self, problems):
        super().__init__('; '.join(problems))
        self.problems = list(problems)


def _read(p):
    return p.read_bytes().decode('utf-8').replace('\r\n', '\n')


def artifact_file(kind, title):
    words = title.split(':', 1)[1] if ':' in title else title
    return '%s-%s.html' % (kind, re.sub(r'[^a-z0-9]+', '-', words.lower()).strip('-'))


def check_tokens(css):
    return ['token %s is not defined on :root' % t for t in REQUIRED_TOKENS if t + ':' not in css]


def load_content(record_dir, key, plugin_dir=None):
    d = Path(record_dir) / 'content' / key
    problems, meta, sections, history = [], {}, [], []
    mp = d / 'meta.json'
    if not mp.is_file():
        problems.append('R4.4 content/%s/meta.json is missing' % key)
    else:
        try:
            meta = json.loads(_read(mp))
        except ValueError:
            problems.append('R4.4 meta.json is not valid JSON')
        for field in ('title', 'hero', 'lede'):
            if not isinstance(meta.get(field), str) or not meta[field].strip():
                problems.append('R4.4 meta.json: "%s" must be a non-empty string' % field)
    n = 0
    for p in sorted(d.glob('*.html')) if d.is_dir() else []:
        m = re.match(r'^(\d\d)-[a-z0-9-]+\.html$', p.name)
        if not m:
            problems.append('R4.1 %s is not named NN-slug.html' % p.name)
            continue
        n += 1
        if int(m.group(1)) != n:
            problems.append('R5.2 sections must be numbered 01..N without gaps')
        text = _read(p)
        first, _, rest = text.partition('\n')
        mt = re.match(r'^<!-- title: (.+) -->$', first)
        if not mt:
            problems.append('R4.10 %s: first line must be a title comment' % p.name)
            continue
        if re.search(r'<script|<style', text, re.I):
            problems.append('R4.10 %s contains <script> or <style>' % p.name)
        sections.append({'title': mt.group(1), 'html': rest})
    hp = d / 'history.json'
    if hp.is_file():
        history = json.loads(_read(hp))
    if problems:
        raise ContentError(problems)
    return {'meta': meta, 'sections': sections, 'history': history}


def check_html(html, key, manifest, registry, plugin_dir, record_dir):
    out = []
    want = 'Full Progress: ' if key == 'full-progress' else 'Feature: '
    m = re.search(r'<title>(.*?)</title>', html)
    if not m or not m.group(1).startswith(want):
        out.append(('R5.1', 'title must start with "%s"' % want))
    if 'FAKE-BAD-HTML' in html:
        out.append(('R5.3', 'the fake checker found its marker'))
    m = re.search(r'<script type="application/json" id="task-registry">(.*?)</script>', html, re.S)
    if key == 'full-progress':
        if not m:
            out.append(('R5.9', 'the full-progress artifact must embed the registry'))
        elif json.loads(m.group(1).replace('<\\/', '</')) != registry:
            out.append(('R5.9', 'the embedded registry differs from the task registry'))
    return out


def render_artifact(manifest, registry, contents, key, plugin_dir, record_dir, stamp_text, stamp_iso):
    esc = _h.escape
    if manifest.get('design') == 'design.css':
        bad = check_tokens((Path(record_dir) / 'design.css').read_text(encoding='utf-8'))
        if bad:
            raise ContentError(['design: ' + b for b in bad])
    fp = key == 'full-progress'
    entry = manifest['full_progress_artifact'] if fp else next(
        e for e in manifest['feature_artifacts'] if e['key'] == key)
    c = contents[key]
    tasks = registry['tasks'] if fp else [t for t in registry['tasks'] if t['owner'] == key]
    order = {s: i for i, s in enumerate(STATUSES)}
    tasks = sorted(tasks, key=lambda t: (order[t['status']], t['id']))
    urls = {e['key']: e['url'] for e in manifest['feature_artifacts']}
    needs = ['%s %s' % (t['id'], t['item']) for t in tasks if t['status'] in ('Needs you', 'Failed')]
    out = ['<title>%s</title>' % esc(entry['title']),
           '<h1>%s</h1>' % esc(c['meta'].get('hero', '')),
           '<h2>0. Status and checklist</h2>',
           '<p>Last update: <time datetime="%s">%s</time> (%s)</p>' % (
               stamp_iso, stamp_text, esc(manifest['timezone_label'])),
           '<p>%s %s</p>' % (esc(c['meta'].get('lede', '')),
                             ('Needs you: ' + '; '.join(needs)) if needs else 'Nothing needs you.')]
    out.append('<table><tr><th>Status</th><th>Item</th><th>Detail</th><th>Expected</th></tr>')
    for t in tasks:
        item = esc(t['item'])
        if fp and t['owner'] in urls and urls[t['owner']]:
            item = '<a href="%s">%s</a>' % (esc(urls[t['owner']]), item)
        out.append('<tr><td>%s</td><td>%s %s</td><td>%s</td><td>%s</td></tr>' % (
            esc(t['status']), esc(t['id']), item, esc(t['detail']), esc(t['expected'])))
    out.append('</table>')
    n = 1
    if fp:
        out.append('<h2>1. Features</h2>')
        for e in manifest['feature_artifacts']:
            out.append('<p>%s %s %s</p>' % (esc(e['title']), esc(e['url']),
                                          esc(contents[e['key']]['meta'].get('lede', '').split('.')[0])))
        n = 2
    for s in c['sections']:
        out.append('<h2>%d. %s</h2>\n%s' % (n, esc(s['title']), s['html']))
        n += 1
    if not fp:
        out.append('<h2>%d. History</h2><table><tr><th>Date</th><th>Change</th></tr>' % n)
        for h in c['history']:
            out.append('<tr><td>%s</td><td>%s</td></tr>' % (esc(h['date']), esc(h['change'])))
        out.append('</table>')
    if fp:      # R5.9: the whole registry, `updated` included
        out.append('<script type="application/json" id="task-registry">%s</script>' %
                   json.dumps(registry, ensure_ascii=False, indent=1).replace('</', '<\\/'))
    return '\n'.join(out) + '\n'
'''

RULE_TEXT = '- Record work as a task before starting it.\n'


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------

def _rmtree(path):
    def onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=onerror)


class Res:
    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err

    @property
    def all(self):
        return self.out + self.err

    def json(self):
        return json.loads(self.out)


def base_env(extra=None):
    env = dict(os.environ)
    env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': str(TMP / 'nullconfig'),
                'GIT_TERMINAL_PROMPT': '0', 'CLAUDE_ARTIFACTS_NOW': NOW})
    for k in ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL',
              'CLAUDE_ARTIFACTS_NO_ZONEINFO', 'CLAUDE_ARTIFACTS_NO_POWERSHELL', 'GIT_DIR', 'GIT_WORK_TREE'):
        env.pop(k, None)
    env.update(extra or {})
    return env


def git(cwd, *a, check=True):
    env = base_env({'GIT_AUTHOR_NAME': 'Seed', 'GIT_AUTHOR_EMAIL': 'seed@example.com',
                    'GIT_COMMITTER_NAME': 'Seed', 'GIT_COMMITTER_EMAIL': 'seed@example.com'})
    r = subprocess.run(['git'] + [str(x) for x in a], cwd=str(cwd), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env)
    if check and r.returncode != 0:
        raise RuntimeError('git %s failed: %s' % (' '.join(map(str, a)), r.stderr))
    return r


class Env:
    """One plugin layout (fake or real renderer) and its throwaway projects."""

    def __init__(self, kind):
        self.kind = kind
        self.n = 0
        self._template = None
        if kind == 'fake':
            self.plugin = TMP / 'fake-plugin'
            (self.plugin / 'scripts').mkdir(parents=True)
            for sub in ('templates', 'design'):
                if (REAL_PLUGIN / sub).is_dir():
                    shutil.copytree(str(REAL_PLUGIN / sub), str(self.plugin / sub))
            (self.plugin / 'rules').mkdir()
            (self.plugin / 'rules' / 'project-artifacts.md').write_text(RULE_TEXT, encoding='utf-8')
            for f in ('project_artifacts.py', 'artifact_queue.py'):
                shutil.copyfile(str(REAL_PLUGIN / 'scripts' / f), str(self.plugin / 'scripts' / f))
            (self.plugin / 'scripts' / 'render_artifacts.py').write_text(FAKE_RENDER, encoding='utf-8')
        else:
            self.plugin = REAL_PLUGIN
        self.script = self.plugin / 'scripts' / 'project_artifacts.py'

    # -- projects
    def project(self, template=None):
        self.n += 1
        return Project(self, 'p%d' % self.n, template)

    def baseline(self):
        """A new project with the standard record, copied from a template (fast)."""
        if self._template is None:
            p = self.project()
            p.init()
            p.ok('feature-new', '--key', 'artifacts', '--title', 'Artifacts', '--prefix', 'AR', '--apps', 'plugin')
            p.ok('feature-new', '--key', 'site', '--title', 'The site', '--prefix', 'SI', '--apps', 'web,api')
            p.ok('task-add', '--owner', 'artifacts', '--item', 'Spec', '--detail', 'Write it.',
                 '--expected', '10 Oct ~14:15', '--status', 'Running')
            p.ok('task-add', '--owner', 'artifacts', '--item', 'Script', '--detail', 'Build it.',
                 '--expected', '11 Oct')
            p.ok('task-add', '--owner', 'site', '--item', 'Landing', '--detail', 'Ship it.',
                 '--expected', '12 Oct; with copy')
            p.ok('task-add', '--owner', 'project', '--prefix', 'DS', '--item', 'Standards',
                 '--detail', 'Keep them.', '--expected', '13 Oct')
            p.ok('set-task-status', 'AR2', 'Live')
            self._template = p
        return self.project(template=self._template)


class Project:
    def __init__(self, env, name, template=None):
        self.env = env
        self.root = TMP / ('%s-%s' % (env.kind, name))
        self.bare = self.root / 'remote.git'
        self.clone = self.root / 'clone'
        self.root.mkdir(parents=True)
        if template is not None:
            shutil.copytree(str(template.bare), str(self.bare))
            git(self.root, 'clone', '-q', self.bare, self.clone)
            return
        git(self.root, 'init', '-q', '--bare', '-b', 'main', self.bare)
        seed = self.root / 'seed'
        seed.mkdir()
        git(seed, 'init', '-q', '-b', 'main')
        (seed / 'README.md').write_text('seed\n', encoding='utf-8')
        git(seed, 'add', '.')
        git(seed, 'commit', '-q', '-m', 'seed')
        git(seed, 'remote', 'add', 'origin', self.bare)
        git(seed, 'push', '-q', 'origin', 'main')
        git(self.root, 'clone', '-q', self.bare, self.clone)

    def clone_again(self, name):
        d = self.root / name
        git(self.root, 'clone', '-q', self.bare, d)
        return d

    def run(self, *args, cwd=None, env=None):
        r = subprocess.run([sys.executable, str(self.env.script)] + [str(a) for a in args],
                           cwd=str(cwd or self.clone), capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env=base_env(env))
        return Res(r.returncode, r.stdout, r.stderr)

    def ok(self, *args, **kw):
        r = self.run(*args, **kw)
        assert r.code == 0, 'expected exit 0 for %s, got %d\n%s' % (args, r.code, r.all)
        return r

    def init(self, *extra):
        return self.ok('init', '--project', 'Demo', '--timezone', 'Europe/Lisbon', '--label', 'Lisbon',
                       '--windows-timezone', 'GMT Standard Time', '--project-prefix', 'DS', *extra)

    # -- reading the remote
    def show(self, path, ref='main'):
        r = git(self.bare, 'show', '%s:%s' % (ref, path), check=False)
        return r.stdout if r.returncode == 0 else None

    def reg(self, ref='main'):
        return json.loads(self.show('docs/artifacts/registry.json', ref))

    def man(self, ref='main'):
        return json.loads(self.show('docs/artifacts/manifest.json', ref))

    def task(self, tid):
        return next(t for t in self.reg()['tasks'] if t['id'] == tid)

    def head(self):
        return git(self.bare, 'rev-parse', 'main').stdout.strip()

    @property
    def wt(self):
        return self.clone / '.claude' / 'worktrees' / 'artifacts-record'

    @property
    def rdir(self):
        return self.wt / 'docs' / 'artifacts'

    def record_copy(self, name):
        """A copy of the pushed record, for fixtures that damage it."""
        dest = TMP / ('rec-%s-%s-%d' % (self.env.kind, name, self.env.n))
        self.env.n += 1
        if dest.exists():
            _rmtree(dest)
        dest.mkdir(parents=True)
        self.ok('path')
        # the worktree is at origin/main after any command
        shutil.copytree(str(self.rdir), str(dest / 'docs' / 'artifacts'))
        return dest / 'docs' / 'artifacts'


def check_record(env, rec_dir):
    r = subprocess.run([sys.executable, str(env.script), 'check', '--record', str(rec_dir)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=base_env())
    return Res(r.returncode, r.stdout, r.stderr)


# in-process access for the seams (a push race needs a hook between fetch and push)
class InProc:
    def __init__(self, env):
        for m in ('render_artifacts', 'artifact_queue', 'project_artifacts'):
            sys.modules.pop(m, None)
        spec = importlib.util.spec_from_file_location('project_artifacts', str(env.script))
        self.mod = importlib.util.module_from_spec(spec)
        sys.modules['project_artifacts'] = self.mod
        spec.loader.exec_module(self.mod)

    def call(self, cwd, *argv, env=None):
        old_env, old_cwd = dict(os.environ), os.getcwd()
        os.environ.update(base_env(env))
        out, err = io.StringIO(), io.StringIO()
        try:
            os.chdir(str(cwd))
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = self.mod.main([str(a) for a in argv])
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)
        return Res(code, out.getvalue(), err.getvalue())


TESTS = []          # (name, fn, fake_only)


def case(fn=None, fake_only=False):
    def deco(f):
        TESTS.append((f.__name__, f, fake_only))
        return f
    return deco(fn) if fn else deco


def has_line(text, req, file=None):
    for ln in text.splitlines():
        if ln.startswith(req + ' ') and (file is None or (' %s:' % file) in ln):
            return True
    return False


# --------------------------------------------------------------------------
# init, feature-new, task-add
# --------------------------------------------------------------------------

@case
def test_init_creates_record(env):
    p = env.project()
    r = p.init()
    assert 'session checkout changes' in r.out and '.gitignore' in r.out, r.out
    for f in ('manifest.json', 'registry.json', 'README.md', 'content/full-progress/meta.json'):
        assert p.show('docs/artifacts/' + f) is not None, f
    m = p.man()
    assert m['spec'] == 'ARTIFACTSPEC 1.0.0' and m['project'] == 'Demo'
    assert m['full_progress_artifact']['title'] == 'Full Progress: Demo'
    assert m['full_progress_artifact']['file'].startswith('full-progress-')
    assert m['default_branch'] == 'main' and m['merged_status'] == 'Live'
    assert m['project_prefixes'] == ['DS'] and m['feature_artifacts'] == []
    assert p.show('docs/artifacts/' + m['full_progress_artifact']['file']).lstrip().startswith('<title>Full Progress: Demo')
    assert p.reg()['tasks'] == []
    log = git(p.bare, 'log', '-1', '--format=%s', 'main').stdout.strip()
    assert log == 'docs/artifacts: init', log
    # refuses a second time
    r2 = p.run('init', '--project', 'Demo')
    assert r2.code == 1 and 'already exists' in r2.err


@case
def test_init_session_files(env):
    p = env.project()
    git(p.clone, 'config', 'user.email', 'a@b.c')
    r = p.init()
    gi = (p.clone / '.gitignore').read_text(encoding='utf-8')
    assert '.claude/artifacts-queue.json' in gi and '.claude/worktrees/' in gi
    if (env.plugin / 'rules' / 'project-artifacts.md').is_file():
        assert (p.clone / '.claude' / 'rules' / 'project-artifacts.md').is_file()
        assert '.claude/rules/project-artifacts.md' in r.out
    else:
        assert 'not in the plugin yet' in r.out
    status = git(p.clone, 'status', '--porcelain').stdout
    assert 'docs/' not in status and 'worktrees' not in status, status
    # idempotent: a second command reports no session changes
    r2 = p.ok('feature-new', '--key', 'a', '--title', 'A', '--prefix', 'AA', '--apps', 'x')
    assert 'session checkout changes' not in r2.out, r2.out
    assert gi == (p.clone / '.gitignore').read_text(encoding='utf-8')


@case
def test_init_gitignore_existing_content(env):
    p = env.project()
    (p.clone / '.gitignore').write_bytes(b'node_modules/\n.claude/worktrees')
    p.init()
    gi = (p.clone / '.gitignore').read_text(encoding='utf-8')
    assert gi.startswith('node_modules/\n.claude/worktrees\n'), gi
    assert gi.count('.claude/worktrees') == 1 and '.claude/artifacts-queue.json' in gi, gi


@case
def test_feature_new_runs_init_first(env):
    p = env.project()
    r = p.ok('feature-new', '--project', 'Demo', '--timezone', 'Europe/Lisbon', '--windows-timezone',
             'GMT Standard Time', '--key', 'artifacts', '--title', 'Artifacts', '--prefix', 'AR',
             '--apps', 'plugin, docs', '--hero', 'The hero.')
    m = p.man()
    e = m['feature_artifacts'][0]
    assert e['key'] == 'artifacts' and e['title'] == 'Feature: Artifacts' and e['prefix'] == 'AR'
    assert e['apps'] == ['plugin', 'docs'] and e['url'] == '' and e['published_sha256'] == ''
    assert e['file'] == 'feature-artifacts.html', e['file']
    meta = json.loads(p.show('docs/artifacts/content/artifacts/meta.json'))
    assert meta['hero'] == 'The hero.' and meta['title'] == 'Feature: Artifacts'
    assert p.show('docs/artifacts/content/artifacts/01-what-and-why.html').startswith('<!-- title: What and why -->')
    hist = json.loads(p.show('docs/artifacts/content/artifacts/history.json'))
    assert len(hist) == 1 and hist[0]['change'] and len(hist[0]['date']) == 12, hist
    assert p.show('docs/artifacts/feature-artifacts.html') is not None
    assert 'export-content artifacts' in r.out and 'edit-content artifacts' in r.out
    # one commit for init + feature
    msgs = git(p.bare, 'log', '--format=%s', 'main').stdout.split('\n')
    assert msgs[0] == 'docs/artifacts: add feature artifacts' and msgs[1] == 'seed', msgs


@case
def test_feature_new_refusals(env):
    p = env.baseline()
    for args, text in [
        (['--key', 'artifacts', '--title', 'Again', '--prefix', 'ZZ', '--apps', 'x'], 'already exists'),
        (['--key', 'new-one', '--title', 'N', '--prefix', 'AR', '--apps', 'x'], 'already registered'),
        (['--key', 'new-one', '--title', 'N', '--prefix', 'DS', '--apps', 'x'], 'already registered'),
        (['--key', 'Bad Key', '--title', 'N', '--prefix', 'ZZ', '--apps', 'x'], 'lowercase'),
        (['--key', 'full-progress', '--title', 'N', '--prefix', 'ZZ', '--apps', 'x'], 'lowercase'),
        (['--key', 'new-one', '--title', 'N', '--prefix', 'z', '--apps', 'x'], 'capital letters'),
    ]:
        before = p.head()
        r = p.run('feature-new', *args)
        assert r.code == 1 and text in r.err, (args, r.code, r.err)
        assert p.head() == before, 'a refused command must write nothing'


@case
def test_task_add(env):
    p = env.baseline()
    n = len(p.reg()['tasks'])
    r = p.ok('task-add', '--owner', 'artifacts', '--item', 'Hooks', '--detail', 'Three hooks.',
             '--expected', '14 Oct ~09:00')
    assert r.out.strip() == 'AR3', r.out
    t = p.task('AR3')
    assert t['owner'] == 'artifacts' and t['app'] == 'plugin' and t['status'] == 'To do'
    assert t['changed'].startswith('2026-10-10T') and t['item'] == 'Hooks'
    # next free number, project task keeps its prefix
    r = p.ok('task-add', '--owner', 'project', '--item', 'More', '--detail', 'd', '--expected', '15 Oct')
    assert r.out.strip() == 'DS2', r.out
    r = p.ok('task-add', '--owner', 'site', '--item', 'x', '--detail', 'd', '--expected', '15 Oct',
             '--app', 'api', '--status', 'Needs you', '--json')
    assert r.json()['id'] == 'SI2' and p.task('SI2')['app'] == 'api' and p.task('SI2')['status'] == 'Needs you'
    assert len(p.reg()['tasks']) == n + 3
    ids = [t['id'] for t in p.reg()['tasks']]
    assert ids == sorted(ids, key=lambda i: (i.rstrip('0123456789'), int(i.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')))), ids
    # a new project prefix is registered
    p.ok('task-add', '--owner', 'project', '--prefix', 'OPS', '--item', 'x', '--detail', 'd', '--expected', '15 Oct')
    assert 'OPS' in p.man()['project_prefixes']
    assert git(p.bare, 'log', '-1', '--format=%s', 'main').stdout.strip() == 'docs/artifacts: OPS1 To do'
    assert p.run('check').code == 0


@case
def test_task_add_refusals(env):
    p = env.baseline()
    cases = [
        (['--owner', 'artifacts', '--item', 'x', '--detail', 'd', '--expected', 'today'], 'R6.6'),
        (['--owner', 'artifacts', '--item', 'x' * 81, '--detail', 'd', '--expected', '14 Oct'], 'R4.8'),
        (['--owner', 'artifacts', '--item', 'x', '--detail', 'd' * 601, '--expected', '14 Oct'], 'R4.8'),
        (['--owner', 'nobody', '--item', 'x', '--detail', 'd', '--expected', '14 Oct'], 'unknown owner'),
        (['--owner', 'artifacts', '--item', 'x', '--detail', 'd', '--expected', '14 Oct', '--status', 'Merged'], 'Live'),
        (['--owner', 'artifacts', '--prefix', 'SI', '--item', 'x', '--detail', 'd', '--expected', '14 Oct'], 'not the prefix'),
        (['--owner', 'project', '--prefix', 'AR', '--item', 'x', '--detail', 'd', '--expected', '14 Oct'], 'belongs to a feature'),
    ]
    for args, text in cases:
        before = p.head()
        r = p.run('task-add', *args)
        assert r.code == 1 and text in r.all, (args, r.code, r.all)
        assert p.head() == before


@case
def test_task_add_project_prefix_needed(env):
    p = env.project()
    p.ok('init', '--project', 'Demo', '--timezone', 'Europe/Lisbon', '--windows-timezone', 'GMT Standard Time')
    r = p.run('task-add', '--owner', 'project', '--item', 'x', '--detail', 'd', '--expected', '14 Oct')
    assert r.code == 1 and '--prefix' in r.err, r.err


# --------------------------------------------------------------------------
# set-task-status
# --------------------------------------------------------------------------

@case
def test_set_task_status(env):
    p = env.baseline()
    before = p.show('docs/artifacts/feature-artifacts.html')
    r = p.ok('set-task-status', 'AR1', 'Needs you', '--detail', 'Waiting for the owner.',
             '--expected', '12 Oct', '--history', 'Needs a decision.')
    assert 'AR1' in r.out and 'Running -> Needs you' in r.out, r.out
    t = p.task('AR1')
    assert t['status'] == 'Needs you' and t['detail'] == 'Waiting for the owner.' and t['expected'] == '12 Oct'
    assert t['changed'].startswith('2026-10-10T')
    after = p.show('docs/artifacts/feature-artifacts.html')
    assert after != before and 'Needs a decision.' in after
    fp = p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    assert 'Needs you' in fp
    hist = json.loads(p.show('docs/artifacts/content/artifacts/history.json'))
    assert hist[0]['change'] == 'Needs a decision.' and len(hist) == 2     # newest first
    assert p.run('check').code == 0
    # the feature artifact of another owner is not touched
    assert p.show('docs/artifacts/feature-the-site.html') is not None


@case
def test_set_task_status_only_touches_its_artifacts(env):
    p = env.baseline()
    site_before = p.show('docs/artifacts/feature-the-site.html')
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert p.show('docs/artifacts/feature-the-site.html') == site_before
    p.ok('set-task-status', 'DS1', 'Running')       # a project task renders full-progress only
    assert p.show('docs/artifacts/feature-the-site.html') == site_before


@case
def test_status_live_done_sets_expected_date(env):
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Live')
    assert p.task('AR1')['expected'] == '10 Oct', p.task('AR1')
    p.ok('set-task-status', 'SI1', 'Done')
    assert p.task('SI1')['expected'] == '10 Oct'
    p.ok('set-task-status', 'DS1', 'Done', '--expected', '09 Oct; shipped early')
    assert p.task('DS1')['expected'] == '09 Oct; shipped early'
    assert p.run('check').code == 0


@case
def test_status_nearest(env):
    p = env.baseline()
    for word, near in [('Merged', 'Live'), ('Blocked', 'Needs you'), ('In progress', 'Running'),
                       ('Paused', 'On hold'), ('Planned', 'To do'), ('Finished', 'Done'),
                       ('Broken', 'Failed'), ('wating', 'Waiting'), ('live', 'Live')]:
        before = p.head()
        r = p.run('set-task-status', 'AR1', word)
        assert r.code == 1 and 'Nearest allowed status: %s.' % near in r.err, (word, r.err)
        assert p.head() == before
    r = p.run('set-task-status', 'AR1', 'xyzzy')
    assert r.code == 1 and 'is not one of' in r.err and 'Nearest' not in r.err
    r = p.run('set-task-status', 'ZZ9', 'Live')
    assert r.code == 1 and 'unknown task' in r.err


@case
def test_set_task_status_removes_queue_events(env):
    p = env.baseline()
    q = p.clone / '.claude' / 'artifacts-queue.json'
    q.parent.mkdir(exist_ok=True)
    ev = lambda i, s: {'id': i, 'suggested_status': s, 'event': 'e', 'command': 'c', 'time': 't'}
    q.write_text(json.dumps({'events': [ev('AR1', 'Waiting'), ev('AR1', 'Live'), ev('SI1', 'Running')]}), encoding='utf-8')
    r = p.ok('set-task-status', 'AR1', 'Waiting', '--json')
    assert r.json()['removed_events'] == 2
    left = json.loads(q.read_text(encoding='utf-8'))['events']
    assert [e['id'] for e in left] == ['SI1']


# --------------------------------------------------------------------------
# edit-content, render
# --------------------------------------------------------------------------

def dirty(p):
    return [x for x in git(p.wt, 'status', '--porcelain').stdout.splitlines() if x.strip()]


def export(p, key, name):
    dest = TMP / ('exp-%s-%s-%d' % (p.env.kind, name, p.env.n))
    p.env.n += 1
    p.ok('export-content', key, '--to', dest)
    return dest


@case
def test_export_content(env):
    p = env.baseline()
    d = export(p, 'artifacts', 'a')
    assert sorted(x.name for x in d.iterdir()) == ['01-what-and-why.html', 'history.json', 'meta.json']
    assert (d / '01-what-and-why.html').read_text(encoding='utf-8') == p.show(
        'docs/artifacts/content/artifacts/01-what-and-why.html')
    r = p.ok('export-content', 'full-progress', '--to', TMP / ('exp-fp-%s-%d' % (env.kind, env.n)), '--json')
    assert 'meta.json' in r.json()['files']
    # refuses a folder that already has files, and unknown keys; reads nothing it should not
    r = p.run('export-content', 'artifacts', '--to', d)
    assert r.code == 1 and 'empty folder' in r.err, r.err
    r = p.run('export-content', 'nope', '--to', TMP / 'exp-nope')
    assert r.code == 1 and 'unknown artifact key' in r.err
    r = p.run('export-content', '../x', '--to', TMP / 'exp-bad')
    assert r.code == 1


@case
def test_edit_content_from_folder(env):
    p = env.baseline()
    d = export(p, 'artifacts', 'b')
    (d / '02-the-design.html').write_text('<!-- title: The design -->\n<p>Tokens and structure.</p>\n', encoding='utf-8')
    meta = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
    meta['lede'] = 'Design is settled.'
    (d / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
    (d / '01-what-and-why.html').unlink()          # a file missing from the folder is removed from the record
    (d / '01-the-start.html').write_text('<!-- title: The start -->\n<p>First.</p>\n', encoding='utf-8')
    r = p.ok('edit-content', 'artifacts', '--from', d)
    assert 'edit-content artifacts' in r.out
    assert p.show('docs/artifacts/content/artifacts/02-the-design.html') is not None
    assert p.show('docs/artifacts/content/artifacts/01-what-and-why.html') is None
    html = p.show('docs/artifacts/feature-artifacts.html')
    assert 'Tokens and structure.' in html and 'Design is settled.' in html and 'First.' in html
    assert 'Design is settled' in p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    assert git(p.bare, 'log', '-1', '--format=%s', 'main').stdout.strip() == 'docs/artifacts: edit artifacts'
    assert p.run('check').code == 0
    assert dirty(p) == [], dirty(p)
    # the folder is read, never the record worktree: stray edits there are discarded by the reset
    (p.rdir / 'content' / 'artifacts' / '03-stray.html').write_text('<!-- title: Stray -->\n<p>s</p>\n', encoding='utf-8')
    d2 = export(p, 'artifacts', 'c')
    assert not (d2 / '03-stray.html').exists()
    p.ok('edit-content', 'artifacts', '--from', d2)
    assert p.show('docs/artifacts/content/artifacts/03-stray.html') is None


@case
def test_edit_content_invalid_writes_nothing(env):
    p = env.baseline()
    d = export(p, 'artifacts', 'd')
    (d / '02-bad.html').write_text('<!-- title: Bad -->\n<script>alert(1)</script>\n', encoding='utf-8')
    before = p.head()
    r = p.run('edit-content', 'artifacts', '--from', d)
    assert r.code == 1 and 'content/artifacts' in r.err and 'nothing written' in r.err, r.err
    assert p.head() == before and dirty(p) == []
    assert p.show('docs/artifacts/content/artifacts/02-bad.html') is None
    (d / '02-bad.html').write_text('<!-- title: Fixed -->\n<p>ok</p>\n', encoding='utf-8')
    p.ok('edit-content', 'artifacts', '--from', d)
    assert 'Fixed' in p.show('docs/artifacts/feature-artifacts.html')
    r = p.run('edit-content', 'nope', '--from', d)
    assert r.code == 1 and 'unknown artifact key' in r.err
    r = p.run('edit-content', 'artifacts', '--from', TMP / 'no-such-folder')
    assert r.code == 1 and 'not a folder' in r.err
    # a folder without meta.json cannot replace the content
    empty = TMP / ('empty-%s-%d' % (env.kind, env.n))
    env.n += 1
    empty.mkdir()
    r = p.run('edit-content', 'artifacts', '--from', empty)
    assert r.code == 1 and p.head() != before
    assert p.show('docs/artifacts/content/artifacts/meta.json') is not None


@case
def test_stray_worktree_edits_are_discarded(env):
    """R4.13: the reset before each change discards anything left in the record worktree."""
    p = env.baseline()
    p.ok('path')
    (p.rdir / 'content' / 'artifacts' / '02-x.html').write_text('<!-- title: X -->\n<p>x</p>\n', encoding='utf-8')
    (p.rdir / 'registry.json').write_text('{}', encoding='utf-8')
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert p.show('docs/artifacts/content/artifacts/02-x.html') is None
    assert p.task('AR1')['status'] == 'Waiting' and len(p.reg()['tasks']) == 4
    assert dirty(p) == []


@case
def test_render_noop_and_all(env):
    p = env.baseline()
    before = p.head()
    r = p.ok('render')
    assert 'nothing to do' in r.out and p.head() == before
    r = p.ok('render', '--all', '--json', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-11T08:00:00+00:00'})
    assert sorted(r.json()['rendered']) == sorted(['full-progress', 'artifacts', 'site'])
    assert p.head() != before
    assert 'datetime="2026-10-11T09:00+01:00"' in p.show('docs/artifacts/feature-the-site.html') or \
        '2026-10-11T09:00+01:00' in p.show('docs/artifacts/feature-the-site.html')


@case
def test_render_repairs_stale_html(env):
    p = env.baseline()
    # a record whose registry was changed on main by hand: html is stale, render fixes it
    other = p.clone_again('hand')
    reg = json.loads((other / 'docs' / 'artifacts' / 'registry.json').read_text(encoding='utf-8'))
    reg['tasks'][0]['detail'] = 'Edited by hand.'
    (other / 'docs' / 'artifacts' / 'registry.json').write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    git(other, 'commit', '-qam', 'hand edit')
    git(other, 'push', '-q', 'origin', 'main')
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'INV-3', 'feature-artifacts.html'), r.all
    p.ok('render')
    assert 'Edited by hand.' in p.show('docs/artifacts/feature-artifacts.html')
    assert p.run('check').code == 0


# --------------------------------------------------------------------------
# pending, mark-published, queue
# --------------------------------------------------------------------------

@case
def test_pending_and_mark_published(env):
    p = env.baseline()
    r = p.run('pending', '--json')
    assert r.code == 1
    j = r.json()
    assert sorted(j) == ['artifacts', 'queue'] and j['queue'] == []
    assert [a['key'] for a in j['artifacts']] == ['full-progress', 'artifacts', 'site']
    for a in j['artifacts']:
        assert sorted(a) == ['file', 'key', 'path', 'reason', 'title', 'url']
        assert a['reason'] == 'never published' and a['url'] == ''
        assert '/' not in a['file'] and os.sep not in a['file'] and a['file'].endswith('.html')
        assert Path(a['path']).is_absolute() and Path(a['path']).name == a['file']
        assert Path(a['path']).is_file() and Path(a['path']).read_text(encoding='utf-8').startswith('<title>')
    assert j['artifacts'][1]['title'] == 'Feature: Artifacts'
    assert 'pending' in p.run('pending').out or 'publish' in p.run('pending').out
    # publish the features, then the full-progress last
    p.ok('mark-published', 'artifacts', '--url', 'https://claude.ai/artifact/aaa')
    after = p.run('pending', '--json').json()['artifacts']
    # the full-progress artifact links to the feature url, so it changed and is still pending
    assert [a['key'] for a in after] == ['full-progress', 'site'], after
    p.ok('mark-published', 'site', '--url', 'https://claude.ai/artifact/bbb')
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/ccc')
    r = p.run('pending', '--json')
    assert r.code == 0 and r.json() == {'artifacts': [], 'queue': []}, r.out
    m = p.man()
    assert m['feature_artifacts'][0]['url'].endswith('/aaa') and len(m['feature_artifacts'][0]['published_sha256']) == 64
    # the recorded hash is the hash of the pushed file
    import hashlib
    h = hashlib.sha256(p.show('docs/artifacts/feature-artifacts.html').encode('utf-8')).hexdigest()
    assert m['feature_artifacts'][0]['published_sha256'] == h
    assert p.run('check').code == 0
    # a status change makes the touched artifacts pending again with the right reason
    p.ok('set-task-status', 'AR1', 'Waiting')
    again = {a['key']: a for a in p.run('pending', '--json').json()['artifacts']}
    assert sorted(again) == ['artifacts', 'full-progress'], again
    assert again['artifacts']['reason'] == 'changed since last publish'
    assert again['artifacts']['url'].endswith('/aaa')
    # url must be http(s)
    r = p.run('mark-published', 'site', '--url', 'nope')
    assert r.code == 1 and 'http' in r.err
    r = p.run('mark-published', 'ghost', '--url', 'https://x.example/a')
    assert r.code == 1 and 'unknown artifact key' in r.err


@case
def test_pending_queue(env):
    p = env.baseline()
    for k, u in (('full-progress', 'c'), ('artifacts', 'a'), ('site', 'b')):
        p.ok('mark-published', k, '--url', 'https://claude.ai/artifact/' + u)
    for k, u in (('artifacts', 'a'), ('site', 'b'), ('full-progress', 'c')):    # settle link churn
        p.ok('mark-published', k, '--url', 'https://claude.ai/artifact/' + u)
    assert p.run('pending').code == 0
    q = p.clone / '.claude' / 'artifacts-queue.json'
    q.parent.mkdir(exist_ok=True)
    q.write_text(json.dumps({'events': [
        {'id': 'AR1', 'suggested_status': 'Waiting', 'event': 'gh pr ready', 'command': 'gh pr ready', 'time': 't'},
        {'id': 'SI1', 'suggested_status': 'Live', 'event': 'merge', 'command': 'gh pr merge', 'time': 't'}]}), encoding='utf-8')
    r = p.run('pending', '--json')
    assert r.code == 1 and r.json()['artifacts'] == [] and [e['id'] for e in r.json()['queue']] == ['AR1', 'SI1']
    assert 'queued AR1 -> Waiting' in p.run('pending').out
    r = p.ok('queue', 'list', '--json')
    assert len(r.json()['queue']) == 2
    assert 'SI1 -> Live' in p.ok('queue', 'list', '--id', 'SI1').out
    r = p.ok('queue', 'clear', '--id', 'AR1')
    assert 'removed 1' in r.out
    assert [e['id'] for e in json.loads(q.read_text(encoding='utf-8'))['events']] == ['SI1']
    p.ok('queue', 'clear')
    assert p.run('pending').code == 0
    assert 'empty' in p.ok('queue', 'list').out


@case
def test_pending_without_record(env):
    p = env.project()
    d = TMP / ('noexp-%s-%d' % (env.kind, env.n))
    env.n += 1
    empty = TMP / ('noexp-empty-%s-%d' % (env.kind, env.n))
    empty.mkdir()
    for argv in (['pending', '--json'], ['pending'], ['check'], ['path'], ['export-content', 'x', '--to', d],
                 ['render'], ['set-task-status', 'AR1', 'Live'], ['edit-content', 'x', '--from', empty],
                 ['task-add', '--owner', 'project', '--prefix', 'DS', '--item', 'x', '--detail', 'd', '--expected', '14 Oct'],
                 ['mark-published', 'full-progress', '--url', 'https://x.example/a'], ['design', 'set', 'default'],
                 ['commit']):
        r = p.run(*argv)
        assert r.code == 2 and 'no record in this repository' in r.err, (argv, r.code, r.all)
        assert not p.wt.exists(), 'no command may create the record worktree without a record: %s' % argv
    r = p.run('check', '--json')
    assert r.code == 2 and r.json()['ok'] is False
    # init is the exception: it creates the worktree
    p.init()
    assert (p.wt / '.git').exists()


# --------------------------------------------------------------------------
# the record worktree and commits (R4.13 - R4.17)
# --------------------------------------------------------------------------

@case
def test_adopted_url_without_hash(env):
    """R4.3: a url with an empty published_sha256 is an adopted artifact; pending says so."""
    p = env.baseline()
    other = p.clone_again('adopt')
    f = other / 'docs' / 'artifacts' / 'manifest.json'
    edit_json(f, lambda m: feat(m).update(url='https://claude.ai/artifact/adopted'))
    git(other, 'commit', '-qam', 'adopt an existing artifact')
    git(other, 'push', '-q', 'origin', 'main')
    p.ok('render')                      # the full-progress artifact links to the adopted url
    assert p.man()['feature_artifacts'][0]['published_sha256'] == ''
    r = p.run('check')
    assert r.code == 0, r.all
    got = {a['key']: a for a in p.run('pending', '--json').json()['artifacts']}
    assert got['artifacts']['reason'] == 'adopted, not yet published from the record', got
    assert got['artifacts']['url'].endswith('/adopted')
    assert got['site']['reason'] == 'never published'
    p.ok('mark-published', 'artifacts', '--url', 'https://claude.ai/artifact/adopted')
    assert 'artifacts' not in {a['key'] for a in p.run('pending', '--json').json()['artifacts']}


@case
def test_feature_task_may_carry_a_project_prefix(env):
    """R4.6: a task moved into a feature keeps its ID; task-add still uses the feature's prefix."""
    p = env.baseline()
    rec = p.record_copy('moved')
    edit_json(rec / 'registry.json', lambda r: task(r, 'AR1').update(id='DS9'))
    out = check_record(env, rec).out
    assert not has_line(out, 'R4.6'), out
    edit_json(rec / 'registry.json', lambda r: task(r, 'DS9').update(id='QQ9'))
    assert has_line(check_record(env, rec).out, 'R4.6', 'registry.json')
    r = p.ok('task-add', '--owner', 'artifacts', '--item', 'x', '--detail', 'd', '--expected', '14 Oct')
    assert r.out.strip() == 'AR3'
    r = p.run('task-add', '--owner', 'artifacts', '--prefix', 'DS', '--item', 'x', '--detail', 'd', '--expected', '14 Oct')
    assert r.code == 1 and 'not the prefix' in r.err


@case
def test_edit_content_no_change(env):
    p = env.baseline()
    d = export(p, 'artifacts', 'same')
    before = p.head()
    r = p.ok('edit-content', 'artifacts', '--from', d)
    assert 'no change' in r.out, r.out
    assert p.head() == before, 'nothing committed'
    assert p.ok('edit-content', 'artifacts', '--from', d, '--json').json()['changed'] is False
    # CRLF copies of the same files are the same content
    for f in d.iterdir():
        f.write_bytes(f.read_bytes().replace(b'\n', b'\r\n'))
    assert 'no change' in p.ok('edit-content', 'artifacts', '--from', d).out and p.head() == before
    (d / 'meta.json').write_text((d / 'meta.json').read_text(encoding='utf-8').replace('Planned', 'Planned,'), encoding='utf-8')
    p.ok('edit-content', 'artifacts', '--from', d)
    assert p.head() != before


@case
def test_record_worktree_is_sparse(env):
    p = env.baseline()
    p.ok('path')
    assert (p.wt / 'docs' / 'artifacts' / 'manifest.json').is_file()
    assert not (p.wt / 'README.md').exists(), 'only docs/artifacts is checked out'
    assert git(p.wt, 'config', '--get', 'core.sparseCheckout').stdout.strip() == 'true'
    # the session's own checkout is not made sparse
    assert git(p.clone, 'config', '--get', 'core.sparseCheckout', check=False).stdout.strip() != 'true'
    assert (p.clone / 'README.md').is_file()
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert not (p.wt / 'README.md').exists() and p.task('AR1')['status'] == 'Waiting'
    # a worktree made before this fix (not sparse) is converted on the next use
    git(p.wt, 'sparse-checkout', 'disable')
    assert (p.wt / 'README.md').exists()
    p.ok('set-task-status', 'AR1', 'Running')
    assert not (p.wt / 'README.md').exists()


@case
def test_session_checkout_untouched(env):
    p = env.baseline()
    git(p.clone, 'checkout', '-q', '-b', 'AR9-some-task')
    # what init told the session to commit on its branch
    (p.clone / '.gitignore').write_text('.claude/artifacts-queue.json\n.claude/worktrees/\n', encoding='utf-8')
    git(p.clone, 'add', '.gitignore')
    git(p.clone, 'commit', '-q', '-m', 'ignore the artifact queue and record worktree')
    (p.clone / 'work.txt').write_text('wip\n', encoding='utf-8')
    head = git(p.clone, 'rev-parse', 'HEAD').stdout
    status = git(p.clone, 'status', '--porcelain').stdout
    reg_before = (p.clone / 'docs' / 'artifacts' / 'registry.json').read_bytes()
    p.ok('set-task-status', 'AR1', 'Waiting')
    p.ok('task-add', '--owner', 'site', '--item', 'x', '--detail', 'd', '--expected', '14 Oct')
    assert git(p.clone, 'rev-parse', 'HEAD').stdout == head
    assert git(p.clone, 'branch', '--show-current').stdout.strip() == 'AR9-some-task'
    assert git(p.clone, 'status', '--porcelain').stdout == status
    assert (p.clone / 'docs' / 'artifacts' / 'registry.json').read_bytes() == reg_before, 'the session tree is stale by design'
    # the record worktree is a detached worktree of origin/main
    assert git(p.wt, 'rev-parse', 'HEAD').stdout.strip() == p.head()
    assert git(p.wt, 'branch', '--show-current').stdout.strip() == ''


@case
def test_commits_only_docs_artifacts(env):
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Waiting')
    files = git(p.bare, 'show', '--name-only', '--format=', 'main').stdout.split()
    assert files and all(f.startswith('docs/artifacts/') for f in files), files
    # the commit helper refuses a staged path outside the record (R4.14)
    ip = InProc(env)
    mod = ip.mod
    ctx = mod.Ctx(p.clone, 'main')
    (p.wt / 'docs' / 'other.txt').write_text('x\n', encoding='utf-8')
    git(p.wt, 'add', '--sparse', 'docs/other.txt')      # the sparse checkout would refuse it otherwise
    try:
        mod.commit_record(ctx, 'x')
    except mod.Fail as e:
        assert e.code == 1 and 'outside docs/artifacts' in e.msg, e.msg
    else:
        raise AssertionError('commit_record must refuse paths outside docs/artifacts')
    assert git(p.wt, 'diff', '--cached', '--name-only').stdout.strip() == '', 'the refused path is unstaged'
    git(p.wt, 'clean', '-fdq')


@case
def test_commit_identity_fallback(env):
    p = env.baseline()
    r = git(p.bare, 'log', '-1', '--format=%an <%ae>', 'main').stdout.strip()
    assert r == 'project-artifacts <project-artifacts@localhost>', r
    git(p.clone, 'config', 'user.name', 'Real Person')
    git(p.clone, 'config', 'user.email', 'real@example.com')
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert git(p.bare, 'log', '-1', '--format=%an', 'main').stdout.strip() == 'Real Person'


@case
def test_no_push_then_commit(env):
    p = env.baseline()
    before = p.head()
    r = p.ok('set-task-status', 'AR1', 'Waiting', '--no-push')
    assert 'not pushed' in r.out
    assert p.head() == before, 'origin must not move'
    assert git(p.wt, 'rev-parse', 'HEAD').stdout.strip() != before
    assert git(p.wt, 'log', '-1', '--format=%s').stdout.strip() == 'docs/artifacts: AR1 Waiting'
    # a second unpushed change stacks on the first
    p.ok('set-task-status', 'SI1', 'Running', '--no-push')
    assert p.head() == before
    reg = json.loads((p.rdir / 'registry.json').read_text(encoding='utf-8'))
    assert {t['id']: t['status'] for t in reg['tasks']}['AR1'] == 'Waiting'
    # pending reads the record worktree state (the committed change)
    assert p.run('pending').code == 1
    r = p.ok('commit')
    assert 'pushed' in r.out
    assert p.task('AR1')['status'] == 'Waiting' and p.task('SI1')['status'] == 'Running'
    assert p.ok('commit').out.strip() == 'nothing to commit or push'


@case
def test_commit_dirty_with_message(env):
    p = env.baseline()
    p.ok('path')
    reg = json.loads((p.rdir / 'registry.json').read_text(encoding='utf-8'))
    next(t for t in reg['tasks'] if t['id'] == 'AR1')['detail'] = 'Hand detail.'
    (p.rdir / 'registry.json').write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    r = p.run('commit', '--retry')
    assert r.code == 1 and 'uncommitted' in r.err
    # a registry that is invalid is not committed (R7.1)
    next(t for t in reg['tasks'] if t['id'] == 'AR1')['status'] = 'Merged'
    (p.rdir / 'registry.json').write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    r = p.run('commit', '--message', 'docs/artifacts: manual')
    assert r.code == 1 and has_line(r.err, 'R4.7'), r.err
    next(t for t in reg['tasks'] if t['id'] == 'AR1')['status'] = 'Running'
    (p.rdir / 'registry.json').write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    p.ok('commit', '--message', 'docs/artifacts: manual')
    assert git(p.bare, 'log', '-1', '--format=%s', 'main').stdout.strip() == 'docs/artifacts: manual'
    assert p.task('AR1')['detail'] == 'Hand detail.'


@case
def test_protection_refusal_and_retry(env):
    p = env.baseline()
    hook = p.bare / 'hooks' / 'pre-receive'
    hook.write_bytes(b'#!/bin/sh\necho "protected branch: pull request required" >&2\nexit 1\n')
    os.chmod(str(hook), 0o755)
    before = p.head()
    r = p.run('set-task-status', 'AR1', 'Waiting')
    assert r.code == 4, r.all
    assert 'record push refused by main protection' in r.err and '(exit 4)' in r.err, r.err
    assert p.head() == before
    # the change stays committed in the record worktree
    assert git(p.wt, 'log', '-1', '--format=%s').stdout.strip() == 'docs/artifacts: AR1 Waiting'
    assert git(p.wt, 'rev-parse', 'HEAD').stdout.strip() != before
    assert dirty(p) == []
    # still refused, still kept
    r = p.run('commit', '--retry')
    assert r.code == 4
    hook.unlink()
    p.ok('commit', '--retry')
    assert p.task('AR1')['status'] == 'Waiting'
    # a later change after a refusal keeps the kept commit and pushes both
    hook.write_bytes(b'#!/bin/sh\nexit 1\n')
    os.chmod(str(hook), 0o755)
    assert p.run('set-task-status', 'SI1', 'Waiting').code == 4
    hook.unlink()
    p.ok('set-task-status', 'AR2', 'Done')
    assert p.task('SI1')['status'] == 'Waiting' and p.task('AR2')['status'] == 'Done'


@case
def test_push_race_is_retried(env):
    p = env.baseline()
    ip = InProc(env)
    other = p.clone_again('clone-b')
    p.ok('path', cwd=other)
    calls = []

    def hook(ctx, attempt):
        calls.append(attempt)
        if attempt == 1:       # another clone lands a different task between our fetch and our push
            r = p.run('set-task-status', 'SI1', 'Running', cwd=other)
            assert r.code == 0, r.all

    ip.mod._TEST_BEFORE_PUSH = hook
    r = ip.call(p.clone, 'set-task-status', 'AR1', 'Waiting')
    assert r.code == 0, r.all
    assert calls == [1, 2], calls
    assert p.task('AR1')['status'] == 'Waiting' and p.task('SI1')['status'] == 'Running', 'both must land'
    assert p.run('check').code == 0
    # task-add races renumber on re-apply: two clones adding to one feature get different IDs
    calls.clear()

    def hook2(ctx, attempt):
        calls.append(attempt)
        if attempt == 1:
            r = p.run('task-add', '--owner', 'site', '--item', 'B', '--detail', 'd', '--expected', '14 Oct', cwd=other)
            assert r.out.strip() == 'SI2', r.all

    ip.mod._TEST_BEFORE_PUSH = hook2
    r = ip.call(p.clone, 'task-add', '--owner', 'site', '--item', 'A', '--detail', 'd', '--expected', '14 Oct')
    assert r.code == 0 and r.out.strip() == 'SI3', r.all
    assert {t['item'] for t in p.reg()['tasks'] if t['id'] in ('SI2', 'SI3')} == {'A', 'B'}


@case
def test_push_race_exhausted_exit_3(env):
    p = env.baseline()
    ip = InProc(env)
    other = p.clone_again('clone-b')
    n = []

    def hook(ctx, attempt):
        n.append(attempt)
        r = p.run('set-task-status', 'SI1', ['Running', 'Waiting', 'Running', 'Waiting', 'Running'][attempt], cwd=other)
        assert r.code == 0, r.all

    ip.mod._TEST_BEFORE_PUSH = hook
    r = ip.call(p.clone, 'set-task-status', 'AR1', 'Waiting')
    assert r.code == 3, r.all
    assert n == [1, 2, 3, 4], 'one try and three retries: %s' % n
    assert '(exit 3)' in r.err
    assert p.task('AR1')['status'] == 'Running', 'the lost change is not on origin'
    assert dirty(p) == [] and git(p.wt, 'status', '--porcelain', '--branch').stdout.count('ahead') == 0


@case
def test_edit_content_survives_lost_race(env):
    p = env.baseline()
    ip = InProc(env)
    other = p.clone_again('clone-b')
    d = export(p, 'artifacts', 'race')
    (d / '02-extra.html').write_text('<!-- title: Extra -->\n<p>kept</p>\n', encoding='utf-8')

    def hook(ctx, attempt):
        if attempt == 1:
            assert p.run('set-task-status', 'SI1', 'Running', cwd=other).code == 0

    ip.mod._TEST_BEFORE_PUSH = hook
    r = ip.call(p.clone, 'edit-content', 'artifacts', '--from', d)
    assert r.code == 0, r.all
    assert p.show('docs/artifacts/content/artifacts/02-extra.html') is not None
    assert p.task('SI1')['status'] == 'Running'


@case
def test_fetch_failure_is_exit_2(env):
    p = env.baseline()
    git(p.clone, 'remote', 'set-url', 'origin', str(p.root / 'does-not-exist.git'))
    r = p.run('set-task-status', 'AR1', 'Waiting')
    assert r.code == 2 and 'fetch' in r.err, r.all
    # read-only commands fall back to the last fetched state
    r = p.run('pending', '--json')
    assert r.code == 1 and 'artifacts' in r.json(), r.all


@case
def test_runs_from_the_record_worktree_and_subfolders(env):
    p = env.baseline()
    sub = p.clone / 'a' / 'b'
    sub.mkdir(parents=True)
    p.ok('set-task-status', 'AR1', 'Waiting', cwd=sub)
    p.ok('set-task-status', 'AR1', 'Running', cwd=p.wt)
    assert p.task('AR1')['status'] == 'Running'


# --------------------------------------------------------------------------
# determinism, time
# --------------------------------------------------------------------------

@case
def test_determinism(env):
    a, b = env.project(), env.project()
    for p in (a, b):
        p.init()
        p.ok('feature-new', '--key', 'f', '--title', 'The F', '--prefix', 'FF', '--apps', 'x')
        p.ok('task-add', '--owner', 'f', '--item', 'One', '--detail', 'd', '--expected', '11 Oct')
        p.ok('set-task-status', 'FF1', 'Live', '--history', 'Done it.')
    for path in ('manifest.json', 'registry.json', 'README.md', 'feature-the-f.html',
                 a.man()['full_progress_artifact']['file'], 'content/f/history.json'):
        x, y = a.show('docs/artifacts/' + path), b.show('docs/artifacts/' + path)
        assert x is not None and x == y, path
    # rendering twice changes nothing (R7.4)
    before = a.head()
    a.ok('render')
    assert a.head() == before
    # and the pushed bytes are LF only
    assert '\r' not in a.show('docs/artifacts/feature-the-f.html')


def tz_ok():
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo('Europe/Lisbon')
        return True
    except Exception:
        return False


@case
def test_time_summer_and_winter(env):
    if not (tz_ok() or shutil.which('powershell') or shutil.which('pwsh')):
        return SKIP('no zone data and no PowerShell on this machine')
    p = env.project()
    p.init()           # NOW = 2026-10-10 11:39Z -> Lisbon summer time
    assert p.man()['updated'] == '2026-10-10T12:39+01:00', p.man()['updated']
    assert 'datetime="2026-10-10T12:39+01:00"' in p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file']) \
        or '2026-10-10T12:39+01:00' in p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    p.ok('feature-new', '--key', 'w', '--title', 'W', '--prefix', 'WW', '--apps', 'x',
         env={'CLAUDE_ARTIFACTS_NOW': '2026-01-15T12:00:00+00:00'})
    assert p.man()['updated'] == '2026-01-15T12:00+00:00', p.man()['updated']
    assert json.loads(p.show('docs/artifacts/content/w/history.json'))[0]['date'] == '15 Jan 12:00'


@case
def test_time_windows_fallback_when_zoneinfo_fails(env):
    if not (shutil.which('powershell') or shutil.which('pwsh')):
        return SKIP('PowerShell is not installed here')
    p = env.project()
    seam = {'CLAUDE_ARTIFACTS_NO_ZONEINFO': '1'}
    p.ok('init', '--project', 'Demo', '--timezone', 'Europe/Lisbon', '--label', 'Lisbon',
         '--windows-timezone', 'GMT Standard Time', env=seam)
    assert p.man()['updated'] == '2026-10-10T12:39+01:00', p.man()['updated']
    r = p.ok('feature-new', '--key', 'w', '--title', 'W', '--prefix', 'WW', '--apps', 'x',
             env=dict(seam, CLAUDE_ARTIFACTS_NOW='2026-01-15T12:00:00+00:00'))
    assert p.man()['updated'] == '2026-01-15T12:00+00:00' and 'warning' not in r.err, r.err
    # the pushed record is equal to what the zoneinfo path writes (when it is available)
    p.ok('feature-new', '--key', 'v', '--title', 'V', '--prefix', 'VV', '--apps', 'x',
         env=dict(seam, CLAUDE_ARTIFACTS_NOW='2026-07-01T23:30:00+00:00'))
    assert p.man()['updated'] == '2026-07-02T00:30+01:00'      # crosses midnight in Lisbon


@case
def test_time_local_fallback_warns(env):
    p = env.project()
    seam = {'CLAUDE_ARTIFACTS_NO_ZONEINFO': '1', 'CLAUDE_ARTIFACTS_NO_POWERSHELL': '1'}
    r = p.ok('init', '--project', 'Demo', '--timezone', 'Europe/Lisbon', '--label', 'Lisbon',
             '--windows-timezone', 'GMT Standard Time', env=seam)
    assert 'warning' in r.err and 'local time' in r.err, r.err
    u = p.man()['updated']
    assert len(u) == 22 and u.startswith('2026-10-1'), u


@case
def test_time_zoneinfo_path(env):
    if not tz_ok():
        return SKIP('zoneinfo has no tz data on this machine (install tzdata to run this case)')
    p = env.project()
    p.ok('init', '--project', 'Demo', '--timezone', 'Europe/Lisbon', '--label', 'Lisbon',
         '--windows-timezone', 'NO SUCH WINDOWS ZONE')
    assert p.man()['updated'] == '2026-10-10T12:39+01:00'


# --------------------------------------------------------------------------
# check: every record-level check has a fixture that makes it fire
# --------------------------------------------------------------------------

def edit_json(path, fn):
    data = json.loads(path.read_text(encoding='utf-8'))
    fn(data)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def feat(m, key='artifacts'):
    return next(e for e in m['feature_artifacts'] if e['key'] == key)


def task(r, tid):
    return next(t for t in r['tasks'] if t['id'] == tid)


def _drop_fp(m):
    m['full_progress_artifact'] = {}


def _second_fp_entry(m):
    m['feature_artifacts'].append({'key': 'full-progress-2', 'title': 'Full Progress: Again', 'url': '',
                                   'file': 'full-progress-again.html', 'prefix': 'FP', 'apps': [],
                                   'published_sha256': ''})


def _stray_fp_file(rec):
    (rec / 'full-progress-other.html').write_text('<title>Full Progress: Other</title>\n', encoding='utf-8')


def _orphan(rec):
    (rec / 'content' / 'ghost').mkdir()
    (rec / 'content' / 'ghost' / 'meta.json').write_text('{}', encoding='utf-8')


def _no_meta(rec):
    (rec / 'content' / 'site' / 'meta.json').unlink()


def _script_in_section(rec):
    (rec / 'content' / 'site' / '01-what-and-why.html').write_text(
        '<!-- title: What and why -->\n<script>x()</script>\n', encoding='utf-8')


def _design_missing(m):
    m['design'] = 'design.css'


def _html_differs(rec):
    f = rec / 'feature-the-site.html'
    f.write_text(f.read_text(encoding='utf-8') + '<!-- hand -->\n', encoding='utf-8')


def _html_missing(rec):
    (rec / 'feature-the-site.html').unlink()


def _html_no_stamp(rec):
    f = rec / 'feature-the-site.html'
    import re
    f.write_text(re.sub(r'<time\b[^>]*>', '<span>', f.read_text(encoding='utf-8')).replace('</time>', '</span>'),
                 encoding='utf-8')


def _status_in_html(rec):
    f = rec / 'feature-artifacts.html'
    f.write_text(f.read_text(encoding='utf-8').replace('Running', 'Live', 1), encoding='utf-8')


def _reg_status_no_render(rec):
    edit_json(rec / 'registry.json', lambda r: task(r, 'AR1').update(status='Waiting'))


MANIFEST_FIXTURES = [
    ('title prefix', 'R5.1', lambda m: feat(m).update(title='Feat: Artifacts')),
    ('fp title prefix', 'R5.1', lambda m: m['full_progress_artifact'].update(title='Progress: Demo')),
    ('no full-progress', 'INV-2', _drop_fp),
    ('second fp entry', 'INV-2', _second_fp_entry),
    ('key uppercase', 'R4.2', lambda m: feat(m).update(key='Artifacts')),
    ('prefix lowercase', 'R4.2', lambda m: feat(m).update(prefix='ar')),
    ('prefix too long', 'R4.2', lambda m: feat(m).update(prefix='TOOLONG')),
    ('duplicate prefix', 'R4.2', lambda m: feat(m, 'site').update(prefix='AR')),
    ('prefix both feature and project', 'R4.2', lambda m: m['project_prefixes'].append('SI')),
    ('duplicate key', 'R4.2', lambda m: feat(m, 'site').update(key='artifacts')),
    ('missing field', 'R4.2', lambda m: m.pop('timezone_label')),
    ('wrong spec', 'R4.2', lambda m: m.update(spec='ARTIFACTSPEC 0.9')),
    ('merged_status', 'R4.2', lambda m: m.update(merged_status='Shipped')),
    ('design value', 'R4.2', lambda m: m.update(design='fancy')),
    ('bad hash', 'R4.3', lambda m: feat(m).update(url='https://claude.ai/artifact/x', published_sha256='abc')),
    ('hash without url', 'R4.3', lambda m: feat(m).update(published_sha256='a' * 64)),
    ('bad url', 'R4.3', lambda m: feat(m).update(url='ftp://x', published_sha256='a' * 64)),
    ('file name', 'R4.4', lambda m: feat(m).update(file='artifacts.html')),
    ('design.css missing', 'R5.10', _design_missing),
]

REGISTRY_FIXTURES = [
    ('duplicate id', 'R4.5', lambda r: r['tasks'].append(dict(task(r, 'AR1')))),
    ('malformed id', 'R4.5', lambda r: task(r, 'AR1').update(id='ar1')),
    ('unregistered prefix', 'R4.6', lambda r: task(r, 'AR1').update(id='QQ1', owner='project')),
    ('unknown owner', 'R4.6', lambda r: task(r, 'AR1').update(owner='ghost')),
    ('wrong prefix for owner', 'R4.6', lambda r: task(r, 'AR1').update(owner='site')),
    ('bad status', 'R4.7', lambda r: task(r, 'AR1').update(status='Merged')),
    ('bad changed', 'R4.7', lambda r: task(r, 'AR1').update(changed='yesterday')),
    ('item length', 'R4.8', lambda r: task(r, 'AR1').update(item='x' * 81)),
    ('detail length', 'R4.8', lambda r: task(r, 'AR1').update(detail='x' * 601)),
    ('id order', 'R4.9', lambda r: r['tasks'].reverse()),
    ('expected relative word', 'R6.6', lambda r: task(r, 'AR1').update(expected='today')),
    ('expected soon', 'R6.6', lambda r: task(r, 'SI1').update(expected='soon; very')),
    ('one-digit day', 'R6.6', lambda r: task(r, 'SI1').update(expected='2 Oct')),
    ('expected missing month', 'R6.6', lambda r: task(r, 'DS1').update(expected='13')),
    ('expected on a done row', 'R6.7', lambda r: task(r, 'AR2').update(expected='tomorrow')),
    ('registry spec', 'R4.2', lambda r: r.update(spec='x')),
]

RECORD_FIXTURES = [
    ('stray full-progress file', 'INV-2', _stray_fp_file, None),
    ('orphan content folder', 'R4.1', _orphan, 'content/ghost'),
    ('missing meta.json', None, _no_meta, 'content/site'),
    ('script in a section', None, _script_in_section, 'content/site'),
    ('html differs from a fresh render', 'INV-3', _html_differs, 'feature-the-site.html'),
    ('html missing', 'INV-3', _html_missing, 'feature-the-site.html'),
    ('html without stamp', 'INV-3', _html_no_stamp, 'feature-the-site.html'),
    ('status typed into html', 'INV-3', _status_in_html, 'feature-artifacts.html'),
    ('registry changed without render', 'INV-3', _reg_status_no_render, 'feature-artifacts.html'),
]


@case
def test_check_baseline_clean(env):
    p = env.baseline()
    r = p.run('check')
    assert r.code == 0 and 'clean' in r.out, r.all
    r = p.run('check', '--json')
    assert r.code == 0 and r.json() == {'findings': []}
    rec = p.record_copy('baseline')
    assert check_record(env, rec).code == 0
    assert check_record(env, rec.parent.parent).code == 0, 'a repository root is accepted for --record'


@case
def test_check_fixtures(env):
    p = env.baseline()
    base = p.record_copy('fixtures')
    assert check_record(env, base).code == 0
    n = 0

    def fresh(name):
        d = TMP / ('fx-%s-%d' % (env.kind, n))
        if d.exists():
            _rmtree(d)
        shutil.copytree(str(base.parent.parent), str(d))
        return d / 'docs' / 'artifacts'

    for name, req, fn in MANIFEST_FIXTURES:
        rec = fresh(name)
        n += 1
        edit_json(rec / 'manifest.json', fn)
        r = check_record(env, rec)
        assert r.code == 1 and has_line(r.out, req), 'fixture "%s" must report %s:\n%s' % (name, req, r.all)
        assert 'manifest.json' in r.out or req == 'INV-2'
    for name, req, fn in REGISTRY_FIXTURES:
        rec = fresh(name)
        n += 1
        edit_json(rec / 'registry.json', fn)
        r = check_record(env, rec)
        assert r.code == 1 and has_line(r.out, req, 'registry.json'), 'fixture "%s" must report %s:\n%s' % (name, req, r.all)
    for name, req, fn, where in RECORD_FIXTURES:
        rec = fresh(name)
        n += 1
        fn(rec)
        r = check_record(env, rec)
        assert r.code == 1, 'fixture "%s" must fail:\n%s' % (name, r.all)
        if req:
            assert has_line(r.out, req), 'fixture "%s" must report %s:\n%s' % (name, req, r.all)
        if where:
            assert where in r.out, 'fixture "%s" must name %s:\n%s' % (name, where, r.out)
    # the lines have the documented shape: "<REQ>  <file>: <message>"
    rec = fresh('shape')
    edit_json(rec / 'registry.json', lambda r: task(r, 'AR1').update(expected='today'))
    lines = check_record(env, rec).out.strip().splitlines()
    assert any(ln.startswith('R6.6  registry.json: AR1') for ln in lines), lines


@case(fake_only=True)
def test_check_runs_check_html(env):
    p = env.baseline()
    rec = p.record_copy('html')
    f = rec / 'feature-the-site.html'
    f.write_text(f.read_text(encoding='utf-8').replace('<h1>', 'FAKE-BAD-HTML<h1>', 1), encoding='utf-8')
    r = check_record(env, rec)
    assert r.code == 1 and has_line(r.out, 'R5.3', 'feature-the-site.html'), r.all
    assert has_line(r.out, 'INV-3', 'feature-the-site.html')


@case
def test_check_unreadable_exit_2(env):
    p = env.baseline()
    rec = p.record_copy('broken')
    (rec / 'manifest.json').write_text('{ not json', encoding='utf-8')
    r = check_record(env, rec)
    assert r.code == 2 and 'unreadable record' in r.err, r.all
    rec = p.record_copy('missing')
    (rec / 'registry.json').unlink()
    assert check_record(env, rec).code == 2
    assert check_record(env, rec / 'nope').code == 2


@case
def test_one_full_progress(env):
    """INV-2: a project has at most one full-progress artifact and one whenever it has a feature."""
    p = env.baseline()
    m = p.man()
    assert sum(1 for e in m['feature_artifacts'] if e['key'] == 'full-progress') == 0
    assert m['full_progress_artifact']['key'] == 'full-progress'
    # the command line cannot create a second one or a feature without one
    r = p.run('feature-new', '--key', 'full-progress', '--title', 'x', '--prefix', 'ZZ', '--apps', 'a')
    assert r.code == 1
    q = env.project()
    q.ok('feature-new', '--project', 'Demo', '--key', 'a', '--title', 'A', '--prefix', 'AA', '--apps', 'x',
         '--timezone', 'Europe/Lisbon')
    assert q.man()['full_progress_artifact']['key'] == 'full-progress'


@case
def test_validation_before_blocks_writes(env):
    """R7.1: a record that is invalid before the change is not written to."""
    p = env.baseline()
    other = p.clone_again('hand')
    f = other / 'docs' / 'artifacts' / 'registry.json'
    edit_json(f, lambda r: task(r, 'AR1').update(expected='today'))
    git(other, 'commit', '-qam', 'break it')
    git(other, 'push', '-q', 'origin', 'main')
    before = p.head()
    r = p.run('set-task-status', 'SI1', 'Waiting')
    assert r.code == 1 and has_line(r.err, 'R6.6') and 'nothing written' in r.err, r.err
    assert p.head() == before
    r = p.run('set-task-status', 'AR1', 'Waiting', '--expected', '14 Oct')
    assert r.code == 1, 'even the fixing command is refused: the record must be repaired first'


@case
def test_validation_after_blocks_writes(env):
    """R7.1: a change that would make the record invalid is refused and nothing is written."""
    p = env.baseline()
    before = p.head()
    r = p.run('set-task-status', 'AR1', 'Waiting', '--expected', 'soon')
    assert r.code == 1 and has_line(r.err, 'R6.6') and 'nothing written' in r.err, r.err
    assert p.head() == before and dirty(p) == []
    assert p.task('AR1')['status'] == 'Running'
    r = p.run('set-task-status', 'AR1', 'Waiting', '--detail', 'x' * 700)
    assert r.code == 1 and has_line(r.err, 'R4.8'), r.err
    assert p.head() == before and dirty(p) == []
    r = p.run('set-task-status', 'AR1', 'Waiting', '--json', '--expected', 'next week')
    assert r.code == 1 and r.json()['ok'] is False and r.json()['findings'][0]['req'] == 'R6.6'


@case
def test_readme_generated(env):
    p = env.baseline()
    t = p.show('docs/artifacts/README.md')
    assert '# Project artifacts' in t and 'Feature: Artifacts' in t and '(not published)' in t
    assert 'render' in t and 'mark-published' in t and 'same title' in t
    p.ok('mark-published', 'artifacts', '--url', 'https://claude.ai/artifact/aaa')
    assert 'https://claude.ai/artifact/aaa' in p.show('docs/artifacts/README.md')


@case
def test_path_command(env):
    p = env.baseline()
    r = p.ok('path')
    assert Path(r.out.strip()) == p.rdir and (p.rdir / 'manifest.json').is_file()
    assert p.ok('path', '--json').json()['record_dir'] == str(p.rdir)


@case
def test_feature_new_needs_project_when_no_record(env):
    p = env.project()
    before = p.head()
    r = p.run('feature-new', '--key', 'a', '--title', 'A', '--prefix', 'AA', '--apps', 'x')
    assert r.code == 1 and '--project is required' in r.err, r.err
    assert p.head() == before
    # with a record already there --project is not needed
    p.init()
    p.ok('feature-new', '--key', 'a', '--title', 'A', '--prefix', 'AA', '--apps', 'x')


def valid_design(env, marker='#123456'):
    """A token block that satisfies the contract of whichever renderer is under test."""
    base = (REAL_PLUGIN / 'design' / 'default-design.css').read_text(encoding='utf-8') \
        if env.kind == 'real' else ':root { --paper: #fff; --ink: #000; }\n'
    return base + '\n/* %s */\n' % marker


@case
def test_design_set_and_default(env):
    p = env.baseline()
    f = TMP / ('design-%s-%d.css' % (env.kind, env.n))
    env.n += 1
    f.write_text(valid_design(env), encoding='utf-8')
    r = p.ok('design', 'set', f)
    assert 'design.css' in r.out
    assert p.man()['design'] == 'design.css'
    assert p.show('docs/artifacts/design.css') == f.read_text(encoding='utf-8')
    assert git(p.bare, 'log', '-1', '--format=%s', 'main').stdout.strip() == 'docs/artifacts: design design.css'
    files = git(p.bare, 'show', '--name-only', '--format=', 'main').stdout.split()
    assert all(x.startswith('docs/artifacts/') for x in files)
    for name in ('feature-artifacts.html', 'feature-the-site.html', p.man()['full_progress_artifact']['file']):
        assert '#123456' in p.show('docs/artifacts/' + name) or env.kind == 'fake', name
    assert p.run('check').code == 0
    # the same file again changes nothing
    before = p.head()
    assert 'unchanged' in p.ok('design', 'set', f).out and p.head() == before
    # back to the default removes the file
    p.ok('design', 'set', 'default')
    assert p.man()['design'] == 'default' and p.show('docs/artifacts/design.css') is None
    assert p.run('check').code == 0
    before = p.head()
    assert 'unchanged' in p.ok('design', 'set', 'default').out and p.head() == before


@case
def test_design_set_validates_tokens(env):
    p = env.baseline()
    f = TMP / ('bad-design-%s-%d.css' % (env.kind, env.n))
    env.n += 1
    f.write_text(':root { --nothing: 1; }\n', encoding='utf-8')
    before = p.head()
    r = p.run('design', 'set', f)
    assert r.code == 1 and has_line(r.err, 'R5.11') and 'token contract' in r.err, r.err
    assert p.head() == before and p.man()['design'] == 'default'
    r = p.run('design', 'set', TMP / 'no-such.css')
    assert r.code == 1 and 'does not exist' in r.err
    # a design.css that lost its tokens on main is a record finding
    g = TMP / ('ok-design-%s-%d.css' % (env.kind, env.n))
    env.n += 1
    g.write_text(valid_design(env), encoding='utf-8')
    p.ok('design', 'set', g)
    rec = p.record_copy('design')
    (rec / 'design.css').write_text(':root { --nothing: 1; }\n', encoding='utf-8')
    r = check_record(env, rec)
    assert r.code == 1 and has_line(r.out, 'R5.11', 'design.css'), r.all
    (rec / 'design.css').unlink()
    r = check_record(env, rec)
    assert r.code == 1 and has_line(r.out, 'R5.10'), r.all


# --------------------------------------------------------------------------
# the registry's `updated` moves only when a task changes (AR20)
# --------------------------------------------------------------------------

def later(n):
    """A clock n hours after NOW, so a stray `updated` bump shows."""
    return {'CLAUDE_ARTIFACTS_NOW': '2026-10-%02dT%02d:00:00+00:00' % (11 + n // 24, 9 + n % 24)}


@case
def test_session_sequence_ends_clean(env):
    """set-task-status -> pending -> mark-published (features, then full-progress) -> pending 0 and check 0."""
    p = env.baseline()
    for k, u in (('full-progress', 'c'), ('artifacts', 'a'), ('site', 'b')):     # a published starting point
        p.ok('mark-published', k, '--url', 'https://claude.ai/artifact/' + u, env=later(0))
    for k, u in (('artifacts', 'a'), ('site', 'b'), ('full-progress', 'c')):
        p.ok('mark-published', k, '--url', 'https://claude.ai/artifact/' + u, env=later(1))
    assert p.run('pending').code == 0 and p.run('check').code == 0
    p.ok('set-task-status', 'AR1', 'Waiting', env=later(2))
    p.ok('set-task-status', 'SI1', 'Live', env=later(3))
    r = p.run('pending', '--json', env=later(4))
    assert r.code == 1, r.out
    pend = [a['key'] for a in r.json()['artifacts']]
    assert pend == ['full-progress', 'artifacts', 'site'], pend
    for i, k in enumerate(['artifacts', 'site', 'full-progress']):
        p.ok('mark-published', k, '--url', 'https://claude.ai/artifact/' + {'artifacts': 'a', 'site': 'b',
                                                                              'full-progress': 'c'}[k], env=later(5 + i))
    r = p.run('pending', '--json', env=later(9))
    assert r.code == 0 and r.json() == {'artifacts': [], 'queue': []}, r.out
    r = p.run('check', env=later(9))
    assert r.code == 0, r.all


@case
def test_mark_published_leaves_registry_byte_identical(env):
    p = env.baseline()
    before = p.show('docs/artifacts/registry.json')
    upd = p.reg()['updated']
    for i, k in enumerate(['artifacts', 'site', 'full-progress']):
        p.ok('mark-published', k, '--url', 'https://claude.ai/artifact/' + k, env=later(1 + i))
        assert p.show('docs/artifacts/registry.json') == before, k
        assert p.man()['updated'] != upd                      # the manifest's own `updated` does move
    assert p.reg()['updated'] == upd
    assert p.man()['updated'] == '2026-10-11T13:00+01:00', p.man()['updated']      # 12:00 UTC, Lisbon summer time
    assert p.run('check').code == 0


@case
def test_non_task_commands_leave_registry_alone(env):
    p = env.baseline()
    before = p.show('docs/artifacts/registry.json')
    f = TMP / ('regdesign-%s-%d.css' % (env.kind, env.n))
    env.n += 1
    f.write_text(valid_design(env, '#abcdef'), encoding='utf-8')
    p.ok('design', 'set', f, env=later(1))
    assert p.show('docs/artifacts/registry.json') == before and p.run('check').code == 0
    p.ok('design', 'set', 'default', env=later(2))
    assert p.show('docs/artifacts/registry.json') == before and p.run('check').code == 0
    d = export(p, 'artifacts', 'reg')
    (d / '02-more.html').write_text('<!-- title: More -->\n<p>More.</p>\n', encoding='utf-8')
    p.ok('edit-content', 'artifacts', '--from', d, env=later(3))
    assert p.show('docs/artifacts/registry.json') == before and p.run('check').code == 0
    p.ok('render', '--all', env=later(4))
    assert p.show('docs/artifacts/registry.json') == before and p.run('check').code == 0
    p.ok('feature-new', '--key', 'extra', '--title', 'Extra', '--prefix', 'EX', '--apps', 'web', env=later(5))
    assert p.show('docs/artifacts/registry.json') == before and p.run('check').code == 0
    # a task change does move it, and the embedded copy follows
    p.ok('set-task-status', 'AR1', 'Waiting', env=later(6))
    assert p.show('docs/artifacts/registry.json') != before and p.reg()['updated'] == '2026-10-11T16:00+01:00', p.reg()['updated']
    assert p.run('check').code == 0


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------

class Skipped(Exception):
    pass


def SKIP(msg):
    raise Skipped(msg)


def real_available():
    f = REAL_PLUGIN / 'scripts' / 'render_artifacts.py'
    if not f.is_file():
        return 'render_artifacts.py is not in claude/plugins/artifacts/scripts yet'
    r = subprocess.run([sys.executable, '-c', 'import render_artifacts'], cwd=str(f.parent),
                       capture_output=True, text=True)
    if r.returncode != 0:
        return 'render_artifacts.py is not importable: %s' % r.stderr.strip().splitlines()[-1:]
    return None


def run_group(kind):
    env = Env(kind)
    passed = failed = skipped = 0
    for name, fn, fake_only in TESTS:
        if fake_only and kind != 'fake':
            continue
        if ONLY and not any(o in name for o in ONLY):
            continue
        try:
            fn(env)
            passed += 1
            print('PASS  [%s] %s' % (kind, name))
        except Skipped as why:
            skipped += 1
            print('SKIP  [%s] %s: %s' % (kind, name, why))
        except Exception:
            failed += 1
            print('FAIL  [%s] %s' % (kind, name))
            print('      ' + traceback.format_exc().strip().replace('\n', '\n      ')[-1800:])
    return passed, failed, skipped


TMP = None
ONLY = [a for a in sys.argv[1:] if not a.startswith('--')]     # run only cases whose name contains one


def main():
    global TMP
    TMP = Path(tempfile.mkdtemp(prefix='ptest-'))
    (TMP / 'nullconfig').write_text('', encoding='utf-8')
    total_p = total_f = 0
    try:
        if '--real-only' not in sys.argv:
            p, f, s = run_group('fake')
            print('fake renderer: %d passed, %d failed, %d skipped' % (p, f, s))
            total_p += p
            total_f += f
        why = None if '--fake-only' in sys.argv else real_available()
        if '--fake-only' in sys.argv:
            pass
        elif why:
            print('SKIP  [real] the real-renderer group is skipped: %s' % why)
        else:
            p, f, s = run_group('real')
            print('real renderer: %d passed, %d failed, %d skipped' % (p, f, s))
            total_p += p
            total_f += f
    finally:
        _rmtree(TMP)
    print('%d passed, %d failed' % (total_p, total_f))
    return 1 if total_f else 0


if __name__ == '__main__':
    sys.exit(main())
