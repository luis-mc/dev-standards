#!/usr/bin/env python3
"""Prove project_artifacts.py does what ARTIFACTSPEC 1.3.0 section 7 says (R13.1).

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
import re
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

STATUSES = ['Live', 'Built', 'Running', 'Needs you', 'Waiting', 'To do', 'On hold', 'Failed']
REQUIRED_TOKENS = ['--paper', '--ink']


class ContentError(Exception):
    def __init__(self, problems):
        super().__init__('; '.join(problems))
        self.problems = list(problems)
        self.partial = None


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
        if mt.group(1).strip().lower() == 'decisions' and key != 'full-progress':
            problems.append('R5.19 %s: a section titled Decisions is drawn from decisions.json only' % p.name)
        sections.append({'title': mt.group(1), 'html': rest})
    hp = d / 'history.json'
    if hp.is_file():
        history = json.loads(_read(hp))
    content = {'meta': meta, 'sections': sections, 'history': history}
    if problems:
        err = ContentError(problems)
        if meta:
            err.partial = content
        raise err
    return content


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


def render_artifact(manifest, registry, contents, key, plugin_dir, record_dir, stamp_text, stamp_iso, links=None):
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
    hrefs = {e['key']: (links or {}).get(e['key'], (e['file'], ''))[0] for e in manifest['feature_artifacts']}
    shown = {e['key']: (links or {}).get(e['key'], (e['file'], ''))[1] for e in manifest['feature_artifacts']}
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
        if fp and t['owner'] in hrefs:
            item = '<a href="%s">%s</a>' % (esc(hrefs[t['owner']]), item)
            if shown[t['owner']]:
                item += ' <span class="local-path">%s</span>' % esc(shown[t['owner']])
        out.append('<tr><td>%s</td><td>%s %s</td><td>%s</td><td>%s</td></tr>' % (
            esc(t['status']), esc(t['id']), item, esc(t['detail']), esc(t['expected'])))
    out.append('</table>')
    n = 1
    if fp:
        out.append('<h2>1. Features</h2>')
        for e in manifest['feature_artifacts']:
            out.append('<p>%s %s %s</p>' % (esc(e['title']), esc(hrefs[e['key']]),
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
              'CLAUDE_ARTIFACTS_NO_ZONEINFO', 'CLAUDE_ARTIFACTS_NO_POWERSHELL', 'GIT_DIR', 'GIT_WORK_TREE',
              'LUISMC_ARTIFACTS_WORKTREE'):
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
            for f in ('project_artifacts.py', 'artifact_queue.py', 'artifact_retire.py'):
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
    assert '.claude/artifacts-publish/' in gi, gi                      # the publish copy is never committed (R5.31)
    # R10.2, R10.4: the plugin delivers the rule at session start; init copies nothing
    assert not (p.clone / '.claude' / 'rules').exists(), list((p.clone / '.claude').iterdir())
    assert 'rules/' not in r.out, r.out
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
    assert e['apps'] == ['plugin', 'docs'] and 'url' not in e and 'published_sha256' not in e   # never published (R4.3)
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


# --------------------------------------------------------------------------
# the basis of Expected (R6.10)
# --------------------------------------------------------------------------

@case
def test_basis_is_stored(env):
    p = env.baseline()
    r = p.ok('task-add', '--owner', 'artifacts', '--item', 'Hooks', '--detail', 'Three hooks.',
             '--expected', '14 Oct ~09:00', '--basis', 'agent slot ~01:30,   ~1.5 h')
    tid = r.out.strip()
    assert p.task(tid)['expected_basis'] == 'agent slot ~01:30, ~1.5 h', p.task(tid)
    assert 'expected_basis' not in p.task('AR1'), 'no basis, no field'
    # an open row keeps it across a status change between open statuses, and it can change or be cleared
    p.ok('set-task-status', tid, 'Waiting')
    assert p.task(tid)['expected_basis'] == 'agent slot ~01:30, ~1.5 h'
    r = p.ok('set-task-status', tid, 'Running', '--basis', 'CI run, ~20 min', '--json')
    assert p.task(tid)['expected_basis'] == 'CI run, ~20 min' and r.json()['expected_basis'] == 'CI run, ~20 min'
    p.ok('set-task-status', tid, 'Running', '--basis', '')
    assert 'expected_basis' not in p.task(tid)
    assert p.run('check').code == 0


@case
def test_basis_dropped_when_closed(env):
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Running', '--basis', 'owner reply, ~1 day')
    assert p.task('AR1')['expected_basis'] == 'owner reply, ~1 day'
    for status in ('Built', 'Live', 'Failed'):
        p.ok('set-task-status', 'AR1', 'Running', '--basis', 'agent slot')
        r = p.ok('set-task-status', 'AR1', status)
        assert 'expected_basis' not in p.task('AR1'), status
        assert p.run('check').code == 0, status
    # a basis asked for on a row that is not open is ignored with a warning, not stored
    r = p.ok('set-task-status', 'AR1', 'Built', '--basis', 'x')
    assert 'expected_basis' not in p.task('AR1') and '--basis ignored' in r.err, r.err
    r = p.ok('task-add', '--owner', 'artifacts', '--item', 'Done thing', '--detail', 'd', '--expected', '10 Oct',
             '--status', 'Built', '--basis', 'x')
    assert 'expected_basis' not in p.task(r.out.strip()) and '--basis ignored' in r.err, r.err


@case
def test_basis_over_80_refused(env):
    p = env.baseline()
    before = p.head()
    for argv in (['task-add', '--owner', 'artifacts', '--item', 'x', '--detail', 'd', '--expected', '14 Oct'],
                 ['set-task-status', 'AR1', 'Running']):
        r = p.run(*argv, '--basis', 'b' * 81)
        assert r.code == 1 and '80' in r.err, r.all
    assert p.run('set-task-status', 'AR1', 'Running', '--basis', 'b' * 80).code == 0
    assert p.head() != before


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
def test_status_live_built_sets_expected_date(env):
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Live')
    assert p.task('AR1')['expected'] == '10 Oct', p.task('AR1')
    p.ok('set-task-status', 'SI1', 'Built')
    assert p.task('SI1')['expected'] == '10 Oct'
    p.ok('set-task-status', 'DS1', 'Built', '--expected', '09 Oct; shipped early')
    assert p.task('DS1')['expected'] == '09 Oct; shipped early'
    assert p.run('check').code == 0


@case
def test_status_nearest(env):
    p = env.baseline()
    for word, near in [('Merged', 'Live'), ('Blocked', 'Needs you'), ('In progress', 'Running'),
                       ('Paused', 'On hold'), ('Planned', 'To do'), ('Finished', 'Built'),
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


@case
def test_a_writing_command_refreshes_every_stale_page(env):
    """R7.5: a page with an older look (a plugin upgrade changed the templates) is rendered again by the next
    status change, though the change is not about it; an up-to-date page keeps its stamp."""
    p = env.baseline()
    other = p.clone_again('old-look')
    site = other / 'docs' / 'artifacts' / 'feature-the-site.html'
    site.write_text(site.read_text(encoding='utf-8') + '<!-- older template -->\n', encoding='utf-8', newline='\n')
    git(other, 'commit', '-qam', 'older template')
    git(other, 'push', '-q', 'origin', 'main')
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'INV-3', 'feature-the-site.html'), r.all
    r = p.ok('set-task-status', 'AR1', 'Running', '--json', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-11T08:00:00+00:00'})
    assert 'site' in r.json()['rendered'], r.all
    assert 'older template' not in p.show('docs/artifacts/feature-the-site.html')
    assert p.run('check').code == 0
    # nothing stale now: a change to AR1 again renders its own pages only
    r = p.ok('set-task-status', 'AR1', 'Waiting', '--json', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-11T09:00:00+00:00'})
    assert 'site' not in r.json()['rendered'], r.all


# --------------------------------------------------------------------------
# pending, mark-published, queue
# --------------------------------------------------------------------------

def url_path(url):
    """The filesystem path a file:/// URL names (percent-decoded)."""
    from urllib.parse import unquote, urlparse
    assert url.startswith('file:///'), url
    s = unquote(urlparse(url).path)
    return s[1:] if os.name == 'nt' and re.match(r'^/[A-Za-z]:', s) else s


def sha(text):
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


@case
def test_pending_and_mark_published(env):
    """R9.1, R5.31, R5.32: only Full Progress is listed, as its publish copy; the hash is of the committed render."""
    p = env.baseline()
    r = p.run('pending', '--json')
    assert r.code == 1
    j = r.json()
    assert sorted(j) == ['artifacts', 'queue', 'retired'] and j['queue'] == [] and j['retired'] == []
    assert [a['key'] for a in j['artifacts']] == ['full-progress'], j['artifacts']          # a feature is never listed (R9.5)
    a = j['artifacts'][0]
    assert sorted(a) == ['file', 'key', 'kind', 'path', 'reason', 'title', 'url'] and a['kind'] == 'full-progress'
    assert a['reason'] == 'never published' and a['url'] == ''
    assert '/' not in a['file'] and os.sep not in a['file'] and a['file'].endswith('.html')
    copy = Path(a['path'])
    assert copy.is_absolute() and copy.name == a['file'] and copy.is_file()
    assert os.path.samefile(str(copy.parent), str(p.clone / '.claude' / 'artifacts-publish')), copy
    assert 'publish' in p.run('pending').out
    committed = p.show('docs/artifacts/' + a['file'])
    text = copy.read_text(encoding='utf-8')
    assert text.startswith('<title>') and text != committed, 'the copy differs from the committed render in its links'
    # mark Full Progress published; the copy does not make the record look stale (R5.32)
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/ccc')
    r = p.run('pending', '--json')
    assert r.code == 0 and r.json() == {'artifacts': [], 'queue': [], 'retired': []}, r.out
    m = p.man()
    fp = m['full_progress_artifact']
    assert fp['url'].endswith('/ccc') and fp['published_sha256'] == sha(p.show('docs/artifacts/' + fp['file']))
    assert fp['published_sha256'] != sha(copy.read_text(encoding='utf-8')), 'the hash is of the committed render, not of the copy'
    for e in m['feature_artifacts']:
        assert 'url' not in e and 'published_sha256' not in e, e
    assert p.run('check').code == 0
    # a status change makes Full Progress pending again, with the right reason and the url to publish to
    p.ok('set-task-status', 'AR1', 'Waiting')
    again = p.run('pending', '--json').json()['artifacts']
    assert [x['key'] for x in again] == ['full-progress'], again
    assert again[0]['reason'] == 'changed since last publish' and again[0]['url'].endswith('/ccc')
    # a feature status change lists Full Progress only
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/ccc')
    p.ok('set-task-status', 'SI1', 'Live')
    assert [x['key'] for x in p.run('pending', '--json').json()['artifacts']] == ['full-progress']
    # url must be http(s)
    r = p.run('mark-published', 'full-progress', '--url', 'nope')
    assert r.code == 1 and 'http' in r.err
    r = p.run('mark-published', 'ghost', '--url', 'https://x.example/a')
    assert r.code == 1 and 'unknown artifact key' in r.err


@case
def test_pending_never_lists_a_feature_artifact(env):
    """R9.5: not when it is new, not when its file or content changed, not when it was never published."""
    p = env.baseline()
    assert [a['key'] for a in p.run('pending', '--json').json()['artifacts']] == ['full-progress']
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/ccc')
    assert p.run('pending').code == 0
    d = export(p, 'site', 'pendfeat')
    meta = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
    meta['lede'] = 'The site changed. More follows.'
    (d / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
    p.ok('edit-content', 'site', '--from', d)
    assert [a['key'] for a in p.run('pending', '--json').json()['artifacts']] == ['full-progress']   # its lede is quoted in section 1
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/ccc')
    p.ok('feature-new', '--key', 'fresh', '--title', 'Fresh', '--prefix', 'FR', '--apps', 'x')
    assert [a['key'] for a in p.run('pending', '--json').json()['artifacts']] == ['full-progress']
    assert 'feature-fresh.html' not in p.run('pending').out


@case
def test_mark_published_refuses_a_feature_artifact(env):
    """R9.5: a clear message, nothing written."""
    p = env.baseline()
    before = p.head()
    for key in ('artifacts', 'site'):
        r = p.run('mark-published', key, '--url', 'https://claude.ai/artifact/zzz')
        assert r.code == 1 and 'feature artifact' in r.err and 'never published' in r.err, r.all
        assert 'only the full-progress artifact is' in r.err and 'feature-' in r.err, r.err
        assert p.head() == before and dirty(p) == []
    r = p.run('mark-published', 'site', '--url', 'https://claude.ai/artifact/zzz', '--json')
    assert r.code == 1 and r.json()['ok'] is False and 'never published' in r.json()['error']
    assert all('url' not in e for e in p.man()['feature_artifacts'])


@case
def test_publish_copy_links_and_committed_links(env):
    """R5.30, R5.31: relative in the committed file, absolute file:/// in the copy, path text beside each link."""
    need_real(env)
    p = env.baseline()
    a = p.run('pending', '--json').json()['artifacts'][0]
    copy = Path(a['path']).read_text(encoding='utf-8')
    committed = p.show('docs/artifacts/' + a['file'])
    # committed: relative file names only
    assert 'href="feature-artifacts.html"' in committed and 'href="feature-the-site.html"' in committed
    assert 'file:' not in committed and 'class="local-path"' not in committed
    # the copy: absolute file:/// URLs to the feature files, in section 1 and on every feature task
    hrefs = sorted(set(re.findall(r'href="(file:///[^"]+)"', copy)))
    assert [h.rsplit('/', 1)[1] for h in hrefs] == ['feature-artifacts.html', 'feature-the-site.html'], hrefs
    for h in hrefs:
        target = Path(url_path(h))
        assert target.is_absolute() and target.is_file() and target.parent.name == 'artifacts'
        assert os.path.samefile(str(target), str(p.clone / 'docs' / 'artifacts' / target.name)), (h, target)   # the session's checkout
        assert '<span class="local-path">%s</span>' % target.as_posix().replace('&', '&amp;') in copy or \
            re.search(r'<span class="local-path">[^<]*%s</span>' % re.escape(target.name), copy), target
    assert copy.count('class="local-path"') == 2 + 3, copy.count('class="local-path"')   # section 1 (2) + AR1, AR2, SI1
    assert 'href="feature-' not in copy
    # the same page: undo the links and it is the committed render
    back = re.sub(r' <span class="local-path">[^<]*</span>', '', copy)
    for h in hrefs:
        back = back.replace('href="%s"' % h, 'href="%s"' % h.rsplit('/', 1)[1])
    assert back == committed
    # the copy is outside the record and ignored once .gitignore says so (R10.2)
    assert 'does not ignore' in p.run('pending').err
    (p.clone / '.gitignore').write_text('.claude/artifacts-publish/\n', encoding='utf-8')
    assert 'does not ignore' not in p.run('pending').err
    assert 'artifacts-publish' not in git(p.clone, 'status', '--porcelain', '--untracked-files=all').stdout


@case
def test_publish_copy_path_encoding_with_spaces(env):
    """R5.31: a space in the path is %20 in the URL and a plain space in the text; `&` is %26 / &amp;."""
    need_real(env)
    env.baseline()
    q = Project(env, 'a b&c %d' % env.n, env._template)
    a = q.run('pending', '--json').json()['artifacts'][0]
    copy = Path(a['path']).read_text(encoding='utf-8')
    hrefs = sorted(set(re.findall(r'href="(file:///[^"]+)"', copy)))
    assert len(hrefs) == 2 and all('%20' in h and ' ' not in h and '%26' in h and '&' not in h for h in hrefs), hrefs
    for h in hrefs:
        assert os.path.samefile(url_path(h), str(q.clone / 'docs' / 'artifacts' / h.rsplit('/', 1)[1])), h
        assert '\\' not in h                                              # forward slashes only
    assert re.search(r'<span class="local-path">[^<]*a b&amp;c[^<]*feature-artifacts\.html</span>', copy), 'path text keeps the space'
    assert q.run('check').code == 0


@case
def test_publish_copy_falls_back_to_the_record_worktree(env):
    """R5.31: a session checkout that does not have the feature file yet links to the record worktree's."""
    need_real(env)
    p = env.project()
    p.init()
    p.ok('feature-new', '--key', 'a', '--title', 'A', '--prefix', 'AA', '--apps', 'x')
    assert not (p.clone / 'docs').exists()                                  # the session is on a checkout without the record
    a = p.run('pending', '--json').json()['artifacts'][0]
    copy = Path(a['path']).read_text(encoding='utf-8')
    (href,) = sorted(set(re.findall(r'href="(file:///[^"]+)"', copy)))
    target = Path(url_path(href))
    assert target.is_file() and os.path.samefile(str(target), str(p.rdir / 'feature-a.html')), (href, target)


@case
def test_old_feature_urls_migrate(env):
    """R4.18: a manifest whose feature entries hold a url or a hash is read without them, noted by check,
    rewritten by the next writing command, and its feature pages and Full Progress links are rendered again."""
    need_real(env)
    p = env.baseline()
    other = p.clone_again('legacy')
    f = other / 'docs' / 'artifacts' / 'manifest.json'
    edit_json(f, lambda m: (feat(m).update(url='https://claude.ai/artifact/old-a', published_sha256='a' * 64),
                            feat(m, 'site').update(url='https://claude.ai/artifact/old-b')))
    page = other / 'docs' / 'artifacts' / 'feature-artifacts.html'
    page.write_text('<title>Feature: Artifacts</title>\n<time datetime="2026-10-10T12:39+01:00">x</time>\n', encoding='utf-8')
    git(other, 'commit', '-qam', 'a record from before feature artifacts stopped being published')
    git(other, 'push', '-q', 'origin', 'main')
    # check reads it, notes the old fields and finds the old page form
    r = p.run('check', '--json')
    assert r.code == 1, r.all
    j = r.json()
    assert any('artifacts' in n and 'no longer published' in n and 'site' in n for n in j['notes']), j['notes']
    assert any(x['req'] == 'INV-3' and x['file'] == 'feature-artifacts.html' for x in j['findings']), j['findings']
    assert 'note: manifest.json: feature artifact(s) artifacts, site' in p.run('check').out
    # nothing lists a feature artifact, whatever its url said
    assert [x['key'] for x in p.run('pending', '--json').json()['artifacts']] == ['full-progress']
    # the next writing command drops the fields and renders everything again
    p.ok('set-task-status', 'SI1', 'Running')
    m = p.man()
    assert all('url' not in e and 'published_sha256' not in e for e in m['feature_artifacts']), m['feature_artifacts']
    assert p.show('docs/artifacts/feature-artifacts.html').startswith('<!doctype html>')
    assert 'href="feature-artifacts.html"' in p.show('docs/artifacts/' + m['full_progress_artifact']['file'])
    r = p.run('check', '--json')
    j = r.json()
    assert r.code == 0 and j['findings'] == [], r.out
    assert len(j['notes']) == 1 and 'old-a' in j['notes'][0] and 'old-b' in j['notes'][0], j['notes']   # R4.19, R4.22
    assert [e['url'] for e in m['retired']] == ['https://claude.ai/artifact/old-a', 'https://claude.ai/artifact/old-b'], m


@case
def test_pending_queue(env):
    p = env.baseline()
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/c')
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
    """R4.3: a full-progress url with an empty published_sha256 is an adopted artifact; pending says so."""
    p = env.baseline()
    other = p.clone_again('adopt')
    f = other / 'docs' / 'artifacts' / 'manifest.json'
    edit_json(f, lambda m: m['full_progress_artifact'].update(url='https://claude.ai/artifact/adopted'))
    git(other, 'commit', '-qam', 'adopt an existing artifact')
    git(other, 'push', '-q', 'origin', 'main')
    assert p.man()['full_progress_artifact']['published_sha256'] == ''
    r = p.run('check')
    assert r.code == 0, r.all
    got = {a['key']: a for a in p.run('pending', '--json').json()['artifacts']}
    assert list(got) == ['full-progress'], got
    assert got['full-progress']['reason'] == 'adopted, not yet published from the record', got
    assert got['full-progress']['url'].endswith('/adopted')
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/adopted')
    assert p.run('pending', '--json').json()['artifacts'] == []


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


# --------------------------------------------------------------------------
# where the record worktree lives (R4.24 - R4.27)
# --------------------------------------------------------------------------

def same_path(a, b):
    return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))


def worktree_of(p, env=None):
    r = p.ok('worktree', '--json', env=env)
    return r.json()['worktree']


def registered_worktrees(p):
    out = git(p.clone, 'worktree', 'list', '--porcelain').stdout
    return [ln[len('worktree '):] for ln in out.splitlines() if ln.startswith('worktree ')]


def elsewhere(env, name):
    d = TMP / ('wt-%s-%s-%d' % (env.kind, name, env.n))
    env.n += 1
    return d


@case
def test_worktree_setting_default(env):
    p = env.baseline()
    assert same_path(worktree_of(p), p.wt)
    assert p.run('worktree').out.strip() == worktree_of(p)
    # a local file without the key, and an empty variable, leave the default
    (p.clone / '.claude').mkdir(exist_ok=True)
    (p.clone / '.claude' / 'artifacts-local.json').write_text('{"other": 1}\n', encoding='utf-8')
    assert same_path(worktree_of(p, env={'LUISMC_ARTIFACTS_WORKTREE': ''}), p.wt)


@case
def test_worktree_setting_environment(env):
    p = env.baseline()
    where = elsewhere(env, 'env')
    other = elsewhere(env, 'other')
    (p.clone / '.claude').mkdir(exist_ok=True)
    (p.clone / '.claude' / 'artifacts-local.json').write_text(json.dumps({'record_worktree': str(other)}), encoding='utf-8')
    # the variable wins over the local file
    assert same_path(worktree_of(p, env={'LUISMC_ARTIFACTS_WORKTREE': str(where)}), where)
    p.ok('set-task-status', 'AR1', 'Waiting', env={'LUISMC_ARTIFACTS_WORKTREE': str(where)})
    assert (where / 'docs' / 'artifacts' / 'manifest.json').is_file() and not other.exists()


@case
def test_worktree_setting_local_file(env):
    p = env.baseline()
    where = elsewhere(env, 'file')
    (p.clone / '.claude').mkdir(exist_ok=True)
    (p.clone / '.claude' / 'artifacts-local.json').write_text(json.dumps({'record_worktree': str(where)}), encoding='utf-8')
    assert same_path(worktree_of(p), where)
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert (where / 'docs' / 'artifacts' / 'manifest.json').is_file() and p.task('AR1')['status'] == 'Waiting'
    assert not p.wt.exists(), 'the default location is not created when the setting points elsewhere'
    # a session sitting inside the moved worktree still finds the checkout's root
    assert same_path(worktree_of(p, env=None), where)
    r = p.run('worktree', '--json', cwd=where)
    assert r.code == 0 and same_path(r.json()['worktree'], where), r.all


@case
def test_worktree_setting_refused(env):
    p = env.baseline()
    head = p.head()
    (p.clone / '.claude').mkdir(exist_ok=True)
    local = p.clone / '.claude' / 'artifacts-local.json'
    bad_env = ['relative/path', '.', '..' + os.sep + 'x', str(p.clone), str(p.clone.parent), str(p.clone / '.git' / 'x')]
    if os.name == 'nt':
        bad_env += ['\\no-drive', 'C:no-slash']
    for value in bad_env:
        for argv in (['worktree'], ['set-task-status', 'AR1', 'Waiting']):
            r = p.run(*argv, env={'LUISMC_ARTIFACTS_WORKTREE': value})
            assert r.code == 2 and 'LUISMC_ARTIFACTS_WORKTREE' in r.err, (value, argv, r.all)
    assert p.head() == head, 'a refused setting writes nothing'
    for text in ('{"record_worktree": "rel/x"}', '{"record_worktree": ""}', '{"record_worktree": 5}', '[1]', '{not json'):
        local.write_text(text, encoding='utf-8')
        r = p.run('set-task-status', 'AR1', 'Waiting')
        assert r.code == 2 and 'artifacts-local.json' in r.err, (text, r.all)
    assert p.head() == head


@case
def test_init_ignores_the_local_settings_file(env):
    p = env.project()
    p.init()
    gi = (p.clone / '.gitignore').read_text(encoding='utf-8')
    assert '.claude/artifacts-local.json' in gi.splitlines(), gi
    where = elsewhere(env, 'ign')
    (p.clone / '.claude').mkdir(exist_ok=True)
    (p.clone / '.claude' / 'artifacts-local.json').write_text(json.dumps({'record_worktree': str(where)}), encoding='utf-8')
    assert 'artifacts-local' not in git(p.clone, 'status', '--porcelain').stdout


@case
def test_moving_the_worktree_removes_the_old_one(env):
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert (p.wt / '.git').exists() and any(same_path(w, p.wt) for w in registered_worktrees(p))
    first = elsewhere(env, 'first')
    second = elsewhere(env, 'second')
    r = p.ok('set-task-status', 'AR1', 'Running', env={'LUISMC_ARTIFACTS_WORKTREE': str(first)})
    assert 'moved' in r.err, r.err
    assert not p.wt.exists() and not any(same_path(w, p.wt) for w in registered_worktrees(p)), registered_worktrees(p)
    assert (first / 'docs' / 'artifacts' / 'manifest.json').is_file()
    assert any(same_path(w, first) for w in registered_worktrees(p))
    assert p.task('AR1')['status'] == 'Running'
    # an unchanged setting moves nothing
    r = p.ok('set-task-status', 'AR1', 'Waiting', env={'LUISMC_ARTIFACTS_WORKTREE': str(first)})
    assert 'moved' not in r.err, r.err
    # moving again, then back to the default
    p.ok('set-task-status', 'AR1', 'Running', env={'LUISMC_ARTIFACTS_WORKTREE': str(second)})
    assert not first.exists() and (second / '.git').exists()
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert not second.exists() and (p.wt / '.git').exists()
    assert [w for w in registered_worktrees(p) if '.claude' in w.replace('\\', '/') and 'artifacts-record' in w] != []
    assert p.run('check').code == 0


@case
def test_moving_refuses_unpushed_commits(env):
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Waiting', '--no-push')
    where = elsewhere(env, 'unpushed')
    r = p.run('set-task-status', 'AR1', 'Running', env={'LUISMC_ARTIFACTS_WORKTREE': str(where)})
    assert r.code == 1 and 'not pushed' in r.err, r.all
    assert (p.wt / '.git').exists() and not where.exists()
    # the old setting pushes them; then the move goes through
    p.ok('commit', '--retry')
    p.ok('set-task-status', 'AR1', 'Running', env={'LUISMC_ARTIFACTS_WORKTREE': str(where)})
    assert not p.wt.exists() and (where / '.git').exists()


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
    p.ok('set-task-status', 'AR2', 'Built')
    assert p.task('SI1')['status'] == 'Waiting' and p.task('AR2')['status'] == 'Built'


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
    m['feature_artifacts'].append({'key': 'full-progress-2', 'title': 'Full Progress: Again',
                                   'file': 'full-progress-again.html', 'prefix': 'FP', 'apps': []})


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
    ('bad hash', 'R4.3', lambda m: m['full_progress_artifact'].update(url='https://claude.ai/artifact/x', published_sha256='abc')),
    ('hash without url', 'R4.3', lambda m: m['full_progress_artifact'].update(published_sha256='a' * 64)),
    ('bad url', 'R4.3', lambda m: m['full_progress_artifact'].update(url='ftp://x', published_sha256='a' * 64)),
    ('full-progress url missing', 'R4.3', lambda m: m['full_progress_artifact'].pop('url')),
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
    ('basis too long', 'R6.10', lambda r: task(r, 'AR1').update(expected_basis='b' * 81)),
    ('basis empty', 'R6.10', lambda r: task(r, 'AR1').update(expected_basis='  ')),
    ('basis not a string', 'R6.10', lambda r: task(r, 'AR1').update(expected_basis=5)),
    ('basis on a Live row', 'R6.10', lambda r: task(r, 'AR1').update(status='Live', expected='10 Oct', expected_basis='x')),
    ('expected relative word', 'R6.6', lambda r: task(r, 'AR1').update(expected='today')),
    ('expected soon', 'R6.6', lambda r: task(r, 'SI1').update(expected='soon; very')),
    ('one-digit day', 'R6.6', lambda r: task(r, 'SI1').update(expected='2 Oct')),
    ('expected missing month', 'R6.6', lambda r: task(r, 'DS1').update(expected='13')),
    ('expected on a built row', 'R6.7', lambda r: task(r, 'AR2').update(expected='tomorrow')),
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
    assert r.code == 0 and r.json() == {'findings': [], 'notes': []}
    rec = p.record_copy('baseline')
    assert check_record(env, rec).code == 0
    assert check_record(env, rec.parent.parent).code == 0, 'a repository root is accepted for --record'


@case
def test_done_is_a_deprecated_alias_of_built(env):
    """R6.9: Done is accepted, stored as Built, with a note; task-add takes it too."""
    p = env.baseline()
    r = p.ok('set-task-status', 'AR1', 'Done')
    assert p.task('AR1')['status'] == 'Built', p.task('AR1')
    assert 'deprecated' in r.err and 'Built' in r.err, r.all
    r = p.ok('task-add', '--owner', 'site', '--item', 'Old', '--detail', 'x', '--expected', '14 Oct',
             '--status', 'done')
    assert p.reg()['tasks'][-1]['status'] == 'Built' and 'deprecated' in r.err, r.all
    r = p.run('set-task-status', 'AR1', 'Finished')            # a synonym is refused, with the hint
    assert r.code == 1 and 'Nearest allowed status: Built' in r.err, r.all
    assert 'Done' not in R_STATUSES(env)


def R_STATUSES(env):
    r = subprocess.run([sys.executable, '-c',
                        'import sys; sys.path.insert(0, %r); import render_artifacts as R; print(R.STATUSES)'
                        % str(env.plugin / 'scripts')], capture_output=True, text=True, env=base_env())
    return r.stdout


@case
def test_old_done_records_migrate_to_built(env):
    """R6.9: a record holding Done is read as Built, noted by check, rewritten by the next writing command."""
    p = env.baseline()
    other = p.clone_again('old-done')
    rp, mp = other / 'docs' / 'artifacts' / 'registry.json', other / 'docs' / 'artifacts' / 'manifest.json'
    reg = json.loads(rp.read_text(encoding='utf-8'))
    next(t for t in reg['tasks'] if t['id'] == 'AR2')['status'] = 'Done'
    rp.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    man = json.loads(mp.read_text(encoding='utf-8'))
    man['merged_status'] = 'Done'
    mp.write_text(json.dumps(man, indent=2) + '\n', encoding='utf-8')
    git(other, 'commit', '-q', '-a', '-m', 'age the record to 1.0.0 statuses')
    git(other, 'push', '-q', 'origin', 'main')
    out = p.run('check', '--json').json()
    assert any('AR2' in n and 'Done' in n for n in out['notes']), out
    assert not any('retired status' in f['message'] for f in out['findings']), out    # a note, not a finding
    r = p.run('check')
    assert 'note: registry.json: AR2 still use the retired status Done' in r.out, r.all
    p.ok('set-task-status', 'AR1', 'Running')       # any writing command
    assert p.task('AR2')['status'] == 'Built', p.task('AR2')
    assert all(t['status'] != 'Done' for t in p.reg()['tasks'])
    assert p.man()['merged_status'] == 'Built', p.man()
    assert 'Done' not in p.show('docs/artifacts/registry.json')
    r = p.ok('check', '--json')
    assert r.json() == {'findings': [], 'notes': []}, r.out


@case
def test_check_notes_a_differing_rule_copy(env):
    """R10.5: a project's own copy of the rule that differs is a note, never a finding."""
    p = env.baseline()
    rules = p.clone / '.claude' / 'rules'
    rules.mkdir(parents=True)
    mine = rules / 'project-artifacts.md'
    plugin_rule = env.plugin / 'rules' / 'project-artifacts.md'
    mine.write_bytes(plugin_rule.read_bytes())
    r = p.run('check', '--json')
    assert r.code == 0 and r.json()['notes'] == [], r.all       # identical: nothing to say
    mine.write_text('- An old rule.\n', encoding='utf-8')
    r = p.run('check')
    assert r.code == 0 and 'record is clean' in r.out, r.all    # not a failure
    assert 'note: ' in r.out and '.claude/rules/project-artifacts.md differs' in r.out, r.out
    assert 'delivers the rule at session start' in r.out and 'can be deleted' in r.out, r.out
    r = p.run('check', '--json')
    assert r.code == 0 and r.json()['findings'] == [] and len(r.json()['notes']) == 1, r.all
    mine.unlink()
    assert p.run('check', '--json').json()['notes'] == []


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


def hand_break_registry(p, tag='hand'):
    """Push to main a registry that has a finding (R6.6), as a hand edit or an older version could leave."""
    other = p.clone_again(tag)
    edit_json(other / 'docs' / 'artifacts' / 'registry.json', lambda r: task(r, 'AR1').update(expected='today'))
    git(other, 'commit', '-qam', 'break it')
    git(other, 'push', '-q', 'origin', 'main')


def hand_decisions_sections(p, keys, tag='hand-d'):
    """Push to main a hand-written section titled Decisions in each of the features (R5.19), as a 1.0.0 record can have."""
    other = p.clone_again(tag)
    for key in keys:
        d = other / 'docs' / 'artifacts' / 'content' / key
        n = len(list(d.glob('[0-9][0-9]-*.html'))) + 1
        (d / ('%02d-decisions.html' % n)).write_text('<!-- title: Decisions -->\n<p>By hand.</p>\n', encoding='utf-8')
    git(other, 'add', '-A')
    git(other, 'commit', '-q', '-m', 'hand-written Decisions sections')
    git(other, 'push', '-q', 'origin', 'main')


@case
def test_earlier_findings_do_not_block_a_change(env):
    """R7.1: a writing command may leave the findings the record already had; it says so and writes the change."""
    p = env.baseline()
    hand_break_registry(p)
    before = p.head()
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R6.6'), r.all
    r = p.ok('set-task-status', 'SI1', 'Waiting')
    assert p.head() != before and p.task('SI1')['status'] == 'Waiting'
    assert re.search(r'note: \d earlier findings? remains?; run check', r.out), r.all
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R6.6'), r.all
    # the fixing command is allowed, and ends the finding
    r = p.ok('set-task-status', 'AR1', 'Waiting', '--expected', '14 Oct')
    assert 'earlier finding' not in r.all
    assert p.run('check').code == 0
    assert dirty(p) == []


@case
def test_a_new_finding_is_refused_beside_earlier_ones(env):
    """R7.1: a change that adds a finding is refused and writes nothing, even when the record has others."""
    p = env.baseline()
    hand_break_registry(p)
    before = p.head()
    # the same rule in the same file again: counted, so it is an added finding
    r = p.run('set-task-status', 'SI1', 'Waiting', '--expected', 'soon')
    assert r.code == 1 and has_line(r.err, 'R6.6') and 'nothing written' in r.err, r.err
    assert p.head() == before and dirty(p) == []
    # another rule
    r = p.run('set-task-status', 'SI1', 'Waiting', '--detail', 'x' * 700)
    assert r.code == 1 and has_line(r.err, 'R4.8'), r.err
    assert p.head() == before and dirty(p) == []
    r = p.run('set-task-status', 'SI1', 'Waiting', '--json', '--expected', 'next week')
    out = r.json()
    assert r.code == 1 and out['ok'] is False and {f['req'] for f in out['findings']} == {'R6.6'}, out
    assert not [f for f in out['findings'] if 'AR1' in f['message']], 'only what the change added is printed'
    assert p.head() == before


@case
def test_validation_before_blocks_writes(env):
    """R7.1: a record the change cannot work with is not written to."""
    p = env.baseline()
    other = p.clone_again('hand')
    (other / 'docs' / 'artifacts' / 'registry.json').write_text('{"spec": "x", "tasks": 5}', encoding='utf-8')
    git(other, 'commit', '-qam', 'break it')
    git(other, 'push', '-q', 'origin', 'main')
    before = p.head()
    for args in (('set-task-status', 'SI1', 'Waiting'),
                 ('task-add', '--owner', 'project', '--prefix', 'DS', '--item', 'X', '--detail', 'x', '--expected', '12 Oct')):
        r = p.run(*args)
        assert r.code == 1 and 'Traceback' not in r.err, (args, r.all)
        assert p.head() == before and dirty(p) == []


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
def test_a_record_with_two_stuck_features_repairs_in_two_edits(env):
    """R7.1: two features each hold a hand-written Decisions section (R5.19). Fixing one used to be refused
    because the other still had its finding, so the record could not be migrated."""
    p = env.baseline()
    hand_decisions_sections(p, ['artifacts', 'site'])
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R5.19', 'content/artifacts') and has_line(r.out, 'R5.19', 'content/site'), r.all
    # the other writing commands work meanwhile, for tasks that need no stuck feature's file
    r = p.ok('task-add', '--owner', 'project', '--prefix', 'DS', '--item', 'More', '--detail', 'Later.', '--expected', '14 Oct')
    assert 'note: 2 earlier findings remain; run check' in r.out, r.all
    r = p.ok('set-task-status', 'DS1', 'Waiting', '--json')
    assert r.json()['notes'] == ['2 earlier findings remain; run check'], r.out
    assert 'Waiting' in p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    # a task of a stuck feature would leave that feature's file out of date: refused, nothing written
    before = p.head()
    r = p.run('set-task-status', 'AR1', 'Waiting')
    assert r.code == 1 and 'content/artifacts is invalid; fix it with edit-content' in r.err, r.all
    assert has_line(r.err, 'R5.19', 'content/artifacts') and p.head() == before and dirty(p) == []
    # edit one: allowed, and the other finding stays
    d = export(p, 'artifacts', 'stuck1')
    (d / '02-decisions.html').unlink()
    r = p.ok('edit-content', 'artifacts', '--from', d)
    assert 'note: 1 earlier finding remains; run check' in r.out, r.all
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R5.19', 'content/site') and not has_line(r.out, 'R5.19', 'content/artifacts'), r.all
    assert not has_line(r.out, 'INV-3'), r.all           # the repaired feature was rendered again
    # its tasks can change again, while the other feature is still stuck
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert 'Waiting' in p.show('docs/artifacts/feature-artifacts.html')
    # edit the other: the record is clean
    d = export(p, 'site', 'stuck2')
    (d / '02-decisions.html').unlink()
    r = p.ok('edit-content', 'site', '--from', d)
    assert 'earlier finding' not in r.all
    r = p.run('check')
    assert r.code == 0 and 'clean' in r.out, r.all
    assert dirty(p) == []


@case
def test_a_stuck_feature_is_not_edited_into_a_stuck_one(env):
    """R7.1: edit-content refuses content that is still invalid, and one that adds a second finding."""
    p = env.baseline()
    hand_decisions_sections(p, ['artifacts', 'site'])
    before = p.head()
    d = export(p, 'artifacts', 'still')          # still holds the Decisions section
    (d / 'meta.json').write_text(json.dumps({**json.loads((d / 'meta.json').read_text(encoding='utf-8')),
                                             'lede': 'Changed.'}), encoding='utf-8')
    r = p.run('edit-content', 'artifacts', '--from', d)
    assert r.code == 1 and has_line(r.err, 'R5.19', 'content/artifacts') and 'nothing written' in r.err, r.err
    assert p.head() == before and dirty(p) == []
    d = export(p, 'artifacts', 'worse')
    (d / '03-more.html').write_text('<!-- title: Decisions -->\n<p>again</p>\n', encoding='utf-8')
    r = p.run('edit-content', 'artifacts', '--from', d)
    assert r.code == 1 and 'nothing written' in r.err and p.head() == before, r.all
    # a clean feature cannot be edited into a stuck one either
    q = env.baseline()
    q.ok('feature-new', '--key', 'third', '--title', 'Third', '--prefix', 'TH', '--apps', 'x')
    hand_decisions_sections(q, ['artifacts'], 'hand-q')
    qb = q.head()
    d = export(q, 'third', 'third')
    (d / '02-decisions.html').write_text('<!-- title: Decisions -->\n<p>no</p>\n', encoding='utf-8')
    r = q.run('edit-content', 'third', '--from', d)
    assert r.code == 1 and has_line(r.err, 'R5.19', 'content/third') and q.head() == qb, r.err
    assert not has_line(r.err, 'R5.19', 'content/artifacts'), 'only the added finding is printed'


@case
def test_a_record_that_is_migrating_and_stuck_repairs_one_edit_at_a_time(env):
    """R7.1a: the first writing command on a 1.0.0 record migrates it; a stuck feature waits for its own edit."""
    p = env.baseline()
    hand_decisions_sections(p, ['artifacts', 'site'])
    other = p.clone_again('old-done')
    rp = other / 'docs' / 'artifacts' / 'registry.json'
    edit_json(rp, lambda r: task(r, 'AR2').update(status='Done'))
    git(other, 'commit', '-q', '-a', '-m', 'age the record to 1.0.0 statuses')
    git(other, 'push', '-q', 'origin', 'main')
    d = export(p, 'artifacts', 'mig1')
    (d / '02-decisions.html').unlink()
    r = p.ok('edit-content', 'artifacts', '--from', d)
    assert p.task('AR2')['status'] == 'Built', p.task('AR2')
    assert 'note: 1 earlier finding remains; run check' in r.out and 'not rendered' in r.out and 'site' in r.out, r.all
    r = p.run('check', '--json')
    assert [(f['req'], f['file']) for f in r.json()['findings']] == [('R5.19', 'content/site')], r.out
    d = export(p, 'site', 'mig2')
    (d / '02-decisions.html').unlink()
    p.ok('edit-content', 'site', '--from', d)
    r = p.run('check')
    assert r.code == 0 and 'clean' in r.out, r.all


@case
def test_render_with_earlier_findings(env):
    """R7.1: render repairs what it can and leaves a feature with invalid content alone."""
    p = env.baseline()
    hand_decisions_sections(p, ['site'])
    other = p.clone_again('hand-reg')
    edit_json(other / 'docs' / 'artifacts' / 'registry.json', lambda r: task(r, 'AR1').update(detail='Edited by hand.'))
    git(other, 'commit', '-qam', 'hand edit')
    git(other, 'push', '-q', 'origin', 'main')
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'INV-3', 'feature-artifacts.html') and has_line(r.out, 'R5.19', 'content/site'), r.all
    site_html = p.show('docs/artifacts/feature-the-site.html')
    r = p.ok('render', '--json')
    assert 'artifacts' in r.json()['rendered'] and 'site' not in r.json()['rendered'], r.out
    assert r.json()['notes'][0] == '1 earlier finding remains; run check', r.out
    assert 'not rendered, because its content is invalid: site' in r.json()['notes'][1], r.out
    assert 'Edited by hand.' in p.show('docs/artifacts/feature-artifacts.html')
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R5.19', 'content/site') and not has_line(r.out, 'INV-3'), r.all
    before = p.head()
    r = p.ok('render', '--all', '--json', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-11T08:00:00+00:00'})
    assert sorted(r.json()['rendered']) == ['artifacts', 'full-progress'], r.out
    assert p.show('docs/artifacts/feature-the-site.html') == site_html and p.head() != before
    r = p.ok('render')
    assert 'nothing to do' in r.out and 'note: 1 earlier finding remains; run check' in r.out, r.all
    assert dirty(p) == []


@case
def test_readme_generated(env):
    p = env.baseline()
    t = p.show('docs/artifacts/README.md')
    assert '# Project artifacts' in t and 'Feature: Artifacts' in t and '(not published)' in t
    assert 'render' in t and 'mark-published' in t and 'same title' in t
    assert 'never published' in t and 'standalone HTML file' in t        # R9.5: a feature is a file
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/aaa')
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
    """set-task-status (several) -> pending lists Full Progress once -> mark-published -> pending 0 and check 0."""
    p = env.baseline()
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/c', env=later(0))   # a published starting point
    assert p.run('pending').code == 0 and p.run('check').code == 0
    p.ok('set-task-status', 'AR1', 'Waiting', env=later(2))
    p.ok('set-task-status', 'SI1', 'Live', env=later(3))
    r = p.run('pending', '--json', env=later(4))
    assert r.code == 1, r.out
    pend = [a['key'] for a in r.json()['artifacts']]
    assert pend == ['full-progress'], pend                                  # two changes, one publish (R3.1)
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/c', env=later(5))
    r = p.run('pending', '--json', env=later(9))
    assert r.code == 0 and r.json() == {'artifacts': [], 'queue': [], 'retired': []}, r.out
    r = p.run('check', env=later(9))
    assert r.code == 0, r.all


@case
def test_mark_published_leaves_registry_byte_identical(env):
    p = env.baseline()
    before = p.show('docs/artifacts/registry.json')
    upd = p.reg()['updated']
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/full-progress', env=later(3))
    assert p.show('docs/artifacts/registry.json') == before
    assert p.man()['updated'] != upd                          # the manifest's own `updated` does move
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
# decisions (section 5.4; the real renderer only)
# --------------------------------------------------------------------------

def d_opt(label, **kw):
    out = {'label': label, 'summary': '%s, in a sentence.' % label}
    out.update(kw)
    return out


def d_dec(n, **kw):
    out = {'id': 'D%d' % n, 'question': 'Which layout for the checkout page?', 'asked': '2026-10-09', 'status': 'decided',
           'options': [d_opt('Single page', recommended=True, preview='<pre>+------+\n| Pay  |\n+------+</pre>'), d_opt('Three steps')],
           'chosen': 'Single page', 'decided': '2026-10-10', 'owner_words': 'single page, fewer clicks', 'task': 'AR1'}
    out.update(kw)
    return out


def d_open(n, **kw):
    out = d_dec(n, question='Should History also list decisions?', status='open', chosen=None, decided=None,
                owner_words=None, options=[d_opt('Yes'), d_opt('No', recommended=True)])
    out.update(kw)
    return out


def edit_decisions(p, decisions, name, key='artifacts', extra=None):
    """export-content, write decisions.json (and extra files), return the folder."""
    d = export(p, key, name)
    (d / 'decisions.json').write_text(json.dumps({'decisions': decisions}, indent=1), encoding='utf-8')
    for rel, data in (extra or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(data)
    return d


def need_real(env):
    if env.kind == 'fake':
        SKIP('the stand-in renderer does not know decisions')


@case
def test_decisions_edit_content_renders_and_checks(env):
    need_real(env)
    p = env.baseline()
    d = edit_decisions(p, [d_dec(1), d_open(2, task='AR1')], 'dec1')
    p.ok('set-task-status', 'AR1', 'Needs you', '--expected', '11 Oct')
    r = p.ok('edit-content', 'artifacts', '--from', d)
    assert 'edit-content artifacts' in r.out
    saved = json.loads(p.show('docs/artifacts/content/artifacts/decisions.json'))
    assert [x['id'] for x in saved['decisions']] == ['D1', 'D2']
    html = p.show('docs/artifacts/feature-artifacts.html')
    assert 'Chosen by the owner &middot; 10 Oct' in html and 'single page, fewer clicks' in html and 'Not chosen' in html
    assert html.index('>Decisions</h2>') < html.index('>History</h2>')
    assert 'Needs you: AR1 Spec; D2 Should History also list decisions?' in html, html[html.index('class="lede"'):][:300]
    assert '1 decision open' in p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    r = p.run('check')
    assert r.code == 0 and 'record is clean' in r.out and 'warning' not in r.out, r.all
    assert dirty(p) == [], dirty(p)
    # an export carries decisions.json back out, and writing it back changes nothing
    d2 = export(p, 'artifacts', 'dec1b')
    assert (d2 / 'decisions.json').is_file()
    head = p.head()
    assert 'no change' in p.ok('edit-content', 'artifacts', '--from', d2).out and p.head() == head


@case
def test_decisions_invalid_file_writes_nothing(env):
    need_real(env)
    p = env.baseline()
    before = p.head()
    bad = [
        ('one option', [d_dec(1, options=[d_opt('Single page')])], 'R5.16'),
        ('decided without a choice', [d_dec(1, chosen=None)], 'R5.16'),
        ('duplicate labels', [d_dec(1, options=[d_opt('A'), d_opt('A')], chosen='A')], 'R5.16'),
        ('open with a choice', [d_open(1, chosen='Yes')], 'R5.16'),
        ('two recommended', [d_dec(1, options=[d_opt('A', recommended=True), d_opt('B', recommended=True)], chosen='A')], 'R5.16'),
        ('replaces nothing', [d_dec(1, replaces='D4')], 'R5.18'),
        ('script in a preview', [d_dec(1, options=[d_opt('A', preview='<script>x()</script>'), d_opt('B')], chosen='B')], 'R5.17'),
        ('external image in a preview', [d_dec(1, options=[d_opt('A', preview='<img src="https://x.test/a.png">'), d_opt('B')], chosen='B')], 'R5.17'),
        ('missing image file', [d_dec(1, options=[d_opt('A', image='assets/none.png'), d_opt('B')], chosen='B')], 'R5.17'),
        ('id gap', [d_dec(1), d_dec(3)], 'R5.15'),
    ]
    for name, decisions, req in bad:
        d = edit_decisions(p, decisions, 'bad-' + name.replace(' ', '-'))
        r = p.run('edit-content', 'artifacts', '--from', d)
        assert r.code == 1 and 'nothing written' in r.err and has_line(r.err, req, 'content/artifacts'), (name, r.err)
        assert p.head() == before and dirty(p) == [] and p.show('docs/artifacts/content/artifacts/decisions.json') is None, name
    # a hand-written Decisions section is refused, in any case
    d = export(p, 'artifacts', 'hand')
    (d / '02-decisions.html').write_text('<!-- title: Decisions -->\n<table><tr><td>1</td></tr></table>\n', encoding='utf-8')
    r = p.run('edit-content', 'artifacts', '--from', d)
    assert r.code == 1 and has_line(r.err, 'R5.19', 'content/artifacts') and 'decisions.json' in r.err, r.err
    assert p.head() == before
    # the full-progress artifact has no decisions.json
    d = edit_decisions(p, [d_dec(1)], 'fp-dec', key='full-progress')
    r = p.run('edit-content', 'full-progress', '--from', d)
    assert r.code == 1 and has_line(r.err, 'R5.14', 'content/full-progress'), r.err
    assert p.head() == before


@case
def test_decisions_are_append_only_through_edit_content(env):
    need_real(env)
    p = env.baseline()
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1), d_open(2)], 'ao1'))
    before = p.head()
    # a decision cannot be removed
    r = p.run('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1)], 'ao2'))
    assert r.code == 1 and has_line(r.err, 'R5.15') and 'D2 was removed' in r.err, r.err
    d = export(p, 'artifacts', 'ao3')
    (d / 'decisions.json').unlink()
    r = p.run('edit-content', 'artifacts', '--from', d)
    assert r.code == 1 and 'D1 was removed' in r.err, r.err
    # a decided one cannot change its choice
    r = p.run('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1, chosen='Three steps', owner_words=None), d_open(2)], 'ao4'))
    assert r.code == 1 and 'D1 is decided; its choice cannot change' in r.err, r.err
    assert p.head() == before
    # but an open one can be closed, and a changed mind is a new decision that replaces the old
    closed = d_open(2, status='decided', chosen='No', decided='2026-10-11', owner_words='no, keep them apart')
    new = d_dec(3, question='Which layout, second thoughts?', replaces='D1', options=[d_opt('Single page'), d_opt('Wizard')],
                chosen='Wizard', owner_words='wizard', asked='2026-10-11', decided='2026-10-11')
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1), closed, new], 'ao5'))
    html = p.show('docs/artifacts/feature-artifacts.html')
    assert 'Replaced by D3' in html and 'no, keep them apart' in html
    assert p.run('check').code == 0


@case
def test_decisions_image_assets_round_trip_byte_for_byte(env):
    need_real(env)
    p = env.baseline()
    png = b'\x89PNG\r\n\x1a\n' + b'\r\n' * 5 + bytes(range(256))
    dec = [d_dec(1, options=[d_opt('A', image='assets/a.png'), d_opt('B')], chosen='B', owner_words=None)]
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, dec, 'img1', extra={'assets/a.png': png}))
    r = git(p.bare, 'show', 'main:docs/artifacts/content/artifacts/assets/a.png', check=False)
    shown = subprocess.run(['git', 'show', 'main:docs/artifacts/content/artifacts/assets/a.png'], cwd=str(p.bare),
                           capture_output=True).stdout
    assert shown == png, 'binary assets must not be line-ending converted'
    html = p.show('docs/artifacts/feature-artifacts.html')
    assert 'src="data:image/png;base64,' in html and 'http' not in html[html.index('decision-image'):][:60]
    d = export(p, 'artifacts', 'img2')
    assert (d / 'assets' / 'a.png').read_bytes() == png
    assert 'no change' in p.ok('edit-content', 'artifacts', '--from', d).out
    # an image the decisions do not name may stay in assets/; dropping the folder drops the file
    r = p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, dec, 'img3', extra={'assets/a.png': png, 'assets/b.png': png}))
    assert p.run('check').code == 0
    # assets/ holds files only
    d = export(p, 'artifacts', 'img4')
    (d / 'assets' / 'sub').mkdir()
    r = p.run('edit-content', 'artifacts', '--from', d)
    assert r.code == 1 and 'assets/ holds files only' in r.err, r.err


@case
def test_check_warns_about_an_open_decision_without_a_needs_you_task(env):
    need_real(env)
    p = env.baseline()
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_open(1, task=None)], 'w1'))
    r = p.run('check')
    assert r.code == 0 and 'record is clean' in r.out, r.all                         # a warning is not a finding
    assert 'warning  content/artifacts: D1 is open, but no task in this feature is in Needs you' in r.out, r.out
    j = p.run('check', '--json')
    assert j.code == 0 and j.json()['findings'] == [] and len(j.json()['warnings']) == 1, j.out
    # naming a task that is not in Needs you still warns, and says which
    d = edit_decisions(p, [d_open(1, task='AR1')], 'w1b')
    # D1 exists with task None: only fields other than the choice may change
    p.ok('edit-content', 'artifacts', '--from', d)
    assert 'its task AR1 is not in Needs you' in p.run('check').out
    # a task of another feature does not count
    p.ok('set-task-status', 'SI1', 'Needs you', '--expected', '12 Oct')
    assert 'its task AR1 is not in Needs you' in p.run('check').out
    # once the task waits on the owner, the warning goes
    p.ok('set-task-status', 'AR1', 'Needs you', '--expected', '12 Oct')
    r = p.run('check')
    assert r.code == 0 and r.out.strip() == 'record is clean', r.out
    assert p.run('check', '--json').json() == {'findings': [], 'notes': []}
    # a decision with no task is satisfied by any Needs you task of its feature
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_open(1, task=None), d_open(2, task=None)], 'w2'))
    assert p.run('check').out.strip() == 'record is clean'
    # a closed decision never warns
    p.ok('set-task-status', 'AR1', 'Running', '--expected', '12 Oct')
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(
        p, [d_dec(1, question='Q?', task=None, options=[d_opt('Yes'), d_opt('No')], chosen='Yes', owner_words=None), d_dec(2, task=None)], 'w3'))
    assert p.run('check').out.strip() == 'record is clean'


@case
def test_check_decisions_against_the_record(env):
    need_real(env)
    p = env.baseline()
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1), d_open(2, task='AR1')], 'c1'))
    base = p.record_copy('decisions')
    assert check_record(env, base).code == 0

    def fresh(name):
        dest = TMP / ('dfx-%s-%s' % (env.kind, name))
        if dest.exists():
            _rmtree(dest)
        shutil.copytree(str(base.parent.parent), str(dest))
        return dest / 'docs' / 'artifacts'

    def broken(name, mutate, req, needle):
        rec = fresh(name)
        path = rec / 'content' / 'artifacts' / 'decisions.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        mutate(data['decisions'])
        path.write_text(json.dumps(data), encoding='utf-8')
        r = check_record(env, rec)
        assert r.code == 1 and has_line(r.out, req, 'content/artifacts') and needle in r.out, '%s:\n%s' % (name, r.all)

    broken('task-unknown', lambda ds: ds[0].update(task='AR99'), 'R5.18', 'AR99 is not in the task registry')
    broken('choice', lambda ds: ds[0].update(chosen='Zero steps'), 'R5.16', 'label of one of its options')
    broken('script', lambda ds: ds[0]['options'][0].update(preview='<p onclick="x()">a</p>'), 'R5.17', 'onclick')
    broken('gap', lambda ds: ds.pop(0), 'R5.15', 'no gap')
    # the rendered file is stale after decisions.json changes by hand: INV-3
    rec = fresh('stale')
    path = rec / 'content' / 'artifacts' / 'decisions.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['decisions'][0]['owner_words'] = 'changed after the render'
    path.write_text(json.dumps(data), encoding='utf-8')
    r = check_record(env, rec)
    assert r.code == 1 and has_line(r.out, 'INV-3', 'feature-artifacts.html'), r.all


@case
def test_an_invalid_decisions_file_is_left_alone_until_edit_content_fixes_it(env):
    """R7.1: the other writing commands neither refuse nor render the feature; edit-content repairs it."""
    need_real(env)
    p = env.baseline()
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1)], 'wc1'))
    other = p.clone_again('other')
    path = other / 'docs' / 'artifacts' / 'content' / 'artifacts' / 'decisions.json'
    git(other, 'config', 'core.sparseCheckout', 'false', check=False)
    data = json.loads(path.read_text(encoding='utf-8'))
    data['decisions'][0]['options'] = data['decisions'][0]['options'][:1]       # a single option: invalid
    path.write_text(json.dumps(data), encoding='utf-8')
    git(other, 'add', '-A')
    git(other, 'commit', '-q', '-m', 'break the decisions')
    git(other, 'push', '-q', 'origin', 'main')
    html = p.show('docs/artifacts/feature-artifacts.html')
    for args in (('set-task-status', 'SI1', 'Waiting'), ('task-add', '--owner', 'project', '--prefix', 'DS', '--item', 'X',
                                                          '--detail', 'x', '--expected', '12 Oct'),
                 ('render', '--all')):
        r = p.run(*args, env=later(5) if args[0] == 'render' else None)
        assert r.code == 0 and re.search(r'note: \d earlier findings? remains?; run check', r.out), (args, r.all)
        assert p.show('docs/artifacts/feature-artifacts.html') == html, args
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R5.16', 'content/artifacts'), r.all
    before = p.head()
    r = p.run('set-task-status', 'AR1', 'Waiting')          # it would leave the feature's file out of date
    assert r.code == 1 and 'edit-content' in r.err and p.head() == before, r.all
    # the edit that fixes it is the way out
    r = p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1)], 'wc2'))
    assert 'earlier finding' not in r.all
    assert p.run('check').code == 0
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert 'Waiting' in p.show('docs/artifacts/feature-artifacts.html')


# --------------------------------------------------------------------------
# retired pages, mark-deleted and the old rule copy (R4.19 to R4.23, R10.6)
# --------------------------------------------------------------------------

URL_A = 'https://claude.ai/artifact/old-a'
URL_B = 'https://claude.ai/artifact/old-b'
FP_URL = 'https://claude.ai/artifact/ccc'


def push_manifest(p, name, fn, message='record change'):
    """Change the pushed manifest as another clone (an older plugin, or history) would."""
    other = p.clone_again(name)
    edit_json(other / 'docs' / 'artifacts' / 'manifest.json', fn)
    git(other, 'commit', '-qam', message)
    git(other, 'push', '-q', 'origin', 'main')


def with_old_urls(m):
    feat(m, 'artifacts').update(url=URL_A, published_sha256='a' * 64)
    feat(m, 'site').update(url=URL_B)


def without_urls(m):
    for e in m['feature_artifacts']:
        e.pop('url', None)
        e.pop('published_sha256', None)


def retired_urls(p):
    return [e['url'] for e in p.man().get('retired', [])]


def published_project(env):
    """A baseline project whose Full Progress is published, so that pending exits 0 unless retired pages change it."""
    p = env.baseline()
    p.ok('mark-published', 'full-progress', '--url', FP_URL)
    return p


@case
def test_migration_keeps_feature_urls_as_retired(env):
    """R4.19: the next writing command moves a feature's url to `retired`; the hash is dropped."""
    p = published_project(env)
    push_manifest(p, 'old1', with_old_urls)
    p.ok('set-task-status', 'SI1', 'Running')
    m = p.man()
    assert all('url' not in e and 'published_sha256' not in e for e in m['feature_artifacts']), m['feature_artifacts']
    assert [(e['key'], e['title'], e['url']) for e in m['retired']] == [
        ('artifacts', 'Feature: Artifacts', URL_A), ('site', 'Feature: The site', URL_B)], m['retired']
    for e in m['retired']:
        assert sorted(e) == ['key', 'retired', 'title', 'url'] and re.match(r'^\d{4}-\d\d-\d\dT', e['retired']), e
    assert 'deleted' not in m
    # a second writing command changes nothing about it
    p.ok('set-task-status', 'SI1', 'Waiting')
    assert p.man()['retired'] == m['retired']
    assert p.run('check').code == 0


@case
def test_retired_urls_are_recovered_from_history(env):
    """R4.20: a record already migrated by 1.1.0 to 1.1.2 (urls gone) finds them in the history of manifest.json."""
    p = published_project(env)
    push_manifest(p, 'h1', with_old_urls, 'a 1.0.0 record')
    push_manifest(p, 'h2', without_urls, 'migrated by 1.1.0: the urls are gone')
    assert 'retired' not in p.man()
    r = p.run('pending', '--json')
    assert r.code == 0, r.all                                  # the full-progress artifact is published
    got = r.json()['retired']
    assert [(e['key'], e['url']) for e in got] == [('artifacts', URL_A), ('site', URL_B)], got
    assert all(e['title'].startswith('Feature: ') and e['retired'] for e in got), got
    assert FP_URL not in json.dumps(got)                       # Full Progress's url is never retired
    # read-only commands wrote nothing; the next writing command writes them
    before = p.head()
    p.run('check')
    assert p.head() == before and 'retired' not in p.man()
    p.ok('set-task-status', 'SI1', 'Running')
    assert retired_urls(p) == [URL_A, URL_B], p.man()
    # a later commit does not duplicate them
    p.ok('set-task-status', 'SI1', 'Waiting')
    assert retired_urls(p) == [URL_A, URL_B]
    # a record with nothing in its history is untouched
    q = env.baseline()
    assert q.run('pending', '--json').json()['retired'] == []


@case
def test_recovery_is_bounded_and_ignores_full_progress(env):
    """R4.20: only feature entries count, whatever else the history holds; a url seen twice is listed once."""
    p = published_project(env)
    push_manifest(p, 'b1', lambda m: (feat(m, 'artifacts').update(url=URL_A), m['full_progress_artifact'].update(url=FP_URL + 'x')))
    push_manifest(p, 'b2', lambda m: feat(m, 'site').update(url=URL_A))        # the same url under another key
    push_manifest(p, 'b3', without_urls)
    got = p.run('pending', '--json').json()['retired']
    assert [e['url'] for e in got] == [URL_A], got
    assert FP_URL + 'x' not in json.dumps(got) and FP_URL not in json.dumps(got)


@case
def test_mark_deleted_removes_the_page_for_good(env):
    """R4.21: moved to `deleted`; never listed again, also not by the history recovery."""
    p = published_project(env)
    push_manifest(p, 'd1', with_old_urls)
    p.ok('set-task-status', 'SI1', 'Running')
    assert retired_urls(p) == [URL_A, URL_B]
    before = p.head()
    # refusals change nothing
    for args, word in ((('mark-deleted', 'site', '--url', URL_A), 'belongs to'),
                       (('mark-deleted', '--url', 'https://claude.ai/artifact/never'), 'not in the retired list'),
                       (('mark-deleted', '--url', FP_URL), 'Full Progress'),
                       (('mark-deleted', 'site', '--url', 'nope'), 'http')):
        r = p.run(*args)
        assert r.code == 1 and word in r.err, (args, r.all)
        assert p.head() == before and dirty(p) == []
    r = p.ok('mark-deleted', 'artifacts', '--url', URL_A)
    assert 'recorded' in r.out
    m = p.man()
    assert retired_urls(p) == [URL_B]
    assert len(m['deleted']) == 1 and m['deleted'][0]['key'] == 'artifacts' and m['deleted'][0]['url'] == URL_A, m
    assert re.match(r'^\d{4}-\d\d-\d\dT', m['deleted'][0]['deleted']) and 'gone' not in m['deleted'][0]
    assert p.run('mark-deleted', 'artifacts', '--url', URL_A).code == 1            # no longer retired
    # the history still shows the url, and it does not come back
    assert [e['url'] for e in p.run('pending', '--json').json()['retired']] == [URL_B]
    p.ok('set-task-status', 'SI1', 'Waiting')
    assert retired_urls(p) == [URL_B] and [e['url'] for e in p.man()['deleted']] == [URL_A]
    # the last one, without a key
    p.ok('mark-deleted', '--url', URL_B, '--json')
    assert p.man()['retired'] == [] and [e['url'] for e in p.man()['deleted']] == [URL_A, URL_B]
    assert p.run('pending', '--json').json()['retired'] == []
    assert p.run('check', '--json').json() == {'findings': [], 'notes': []}


@case
def test_mark_deleted_gone(env):
    """R4.21: `--gone` records a page that no longer exists, with the same effect."""
    p = published_project(env)
    push_manifest(p, 'g1', with_old_urls)
    push_manifest(p, 'g2', without_urls)
    r = p.ok('mark-deleted', '--url', URL_B, '--gone')           # recovered from history, then recorded
    m = p.man()
    assert [e['url'] for e in m['retired']] == [URL_A], m
    assert m['deleted'] == [{'key': 'site', 'url': URL_B, 'deleted': m['deleted'][0]['deleted'], 'gone': True}], m
    assert [e['url'] for e in p.run('pending', '--json').json()['retired']] == [URL_A]


@case
def test_pending_lists_retired_pages_without_changing_its_exit_code(env):
    """R4.22: listed apart, with title, url and what to do; exit 0 stays 0 and exit 1 stays 1."""
    p = published_project(env)
    push_manifest(p, 'e1', with_old_urls)
    p.ok('set-task-status', 'SI1', 'Running')                    # migrates; Full Progress changed, so republish
    p.ok('mark-published', 'full-progress', '--url', FP_URL)
    r = p.run('pending')
    assert r.code == 0, r.all
    assert 'nothing pending' in r.out
    lines = [ln for ln in r.out.splitlines() if ln.startswith('retired ')]
    assert len(lines) == 2 and URL_A in lines[0] and 'Feature: Artifacts' in lines[0], lines
    for ln in lines:
        assert 'ask the owner to confirm' in ln and 'Artifact tool (action: delete)' in ln and 'mark-deleted' in ln, ln
    j = p.run('pending', '--json')
    assert j.code == 0 and [e['url'] for e in j.json()['retired']] == [URL_A, URL_B]
    assert sorted(j.json()['retired'][0]) == ['key', 'retired', 'title', 'url']
    # with Full Progress pending the exit code is 1 for that reason alone
    p.ok('set-task-status', 'AR1', 'Waiting')
    r = p.run('pending', '--json')
    assert r.code == 1 and [a['key'] for a in r.json()['artifacts']] == ['full-progress'] and len(r.json()['retired']) == 2
    p.ok('mark-published', 'full-progress', '--url', FP_URL)
    assert p.run('pending').code == 0


@case
def test_check_notes_retired_pages(env):
    """R4.22: a note, never a finding; the exit code is not changed."""
    p = published_project(env)
    push_manifest(p, 'n1', with_old_urls)
    push_manifest(p, 'n2', without_urls)
    r = p.run('check', '--json')
    assert r.code == 0 and r.json()['findings'] == [], r.all
    notes = r.json()['notes']
    assert len(notes) == 1 and URL_A in notes[0] and URL_B in notes[0] and 'mark-deleted' in notes[0], notes
    assert 'owner to confirm' in notes[0] and 'action: delete' in notes[0], notes
    t = p.run('check')
    assert t.code == 0 and 'record is clean' in t.out and 'note: claude.ai pages' in t.out, t.all
    # a malformed list is a finding (R4.19)
    push_manifest(p, 'n3', lambda m: m.update(retired=[{'key': 'x'}], deleted='no'))
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R4.19', 'manifest.json'), r.all


@case
def test_full_progress_url_is_never_retired(env):
    """R4.19, R4.21: Full Progress's url is in neither list, and mark-deleted refuses it."""
    p = published_project(env)
    push_manifest(p, 'f1', lambda m: feat(m, 'site').update(url=FP_URL))        # a feature entry that held Full Progress's url
    p.ok('set-task-status', 'SI1', 'Running')
    m = p.man()
    assert m.get('retired', []) == [] and m['full_progress_artifact']['url'] == FP_URL, m
    r = p.run('mark-deleted', '--url', FP_URL, '--gone')
    assert r.code == 1 and 'Full Progress' in r.err
    assert p.run('pending', '--json').json()['retired'] == []


RULE_1_0_0 = ('# Project artifacts\n\n- Record work as a task before starting it.\n- Start branch names with the task ID.\n'
              '- Change status only with `set-task-status`.\n- Publish what `pending` lists in the same turn.\n'
              '- Never type a status row by hand.\n- Put every doc under `docs/`.\n')
STALE = '.claude/rules/project-artifacts.md'


def push_file(p, name, rel, text):
    other = p.clone_again(name)
    f = other / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(text.encode('utf-8'))
    git(other, 'add', '-A')
    git(other, 'commit', '-qm', 'the rule copy that init 1.0.0 made')
    git(other, 'push', '-q', 'origin', 'main')


@case
def test_stale_rule_copy_is_removed_with_the_migration_commit(env):
    """R10.6: a copy equal to a shipped rule text (any line endings) is deleted in the record commit, and says so."""
    p = env.baseline()
    push_file(p, 's1', STALE, RULE_1_0_0.replace('\n', '\r\n'))
    assert p.show(STALE) is not None
    local = p.clone / STALE                                       # an untracked copy in the session's checkout
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(RULE_1_0_0, encoding='utf-8')
    # a record worktree made by an older script: its sparse checkout names docs/artifacts only
    p.ok('path')
    git(p.wt, 'sparse-checkout', 'set', '--no-cone', '/docs/artifacts/')
    r = p.ok('set-task-status', 'AR1', 'Waiting')
    assert 'removed .claude/rules/project-artifacts.md' in r.out, r.out
    assert p.show(STALE) is None
    msg = git(p.bare, 'log', '-1', '--format=%B', 'main').stdout
    assert 'removed .claude/rules/project-artifacts.md' in msg and 'AR1' in msg, msg
    assert not local.exists(), 'the untracked copy in the checkout is removed too'
    assert p.show('docs/artifacts/manifest.json') is not None
    # the current plugin rule is also a copy that can go
    push_file(p, 's2', STALE, (env.plugin / 'rules' / 'project-artifacts.md').read_text(encoding='utf-8'))
    r = p.ok('render', '--all')
    assert p.show(STALE) is None and 'removed .claude/rules' in r.out, r.out


@case
def test_edited_rule_copy_is_kept(env):
    """R10.6, R10.5: a copy the owner edited stays, and check keeps noting it."""
    p = env.baseline()
    mine = RULE_1_0_0 + '- Also: my own line.\n'
    push_file(p, 'k1', STALE, mine)
    local = p.clone / STALE
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(mine, encoding='utf-8')
    r = p.ok('set-task-status', 'AR1', 'Waiting')
    assert 'removed' not in r.out, r.out
    assert p.show(STALE) == mine and local.read_text(encoding='utf-8') == mine
    c = p.run('check')
    assert c.code == 0 and 'differs' in c.out, c.all


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
