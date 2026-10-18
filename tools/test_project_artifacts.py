#!/usr/bin/env python3
"""Prove project_artifacts.py does what ARTIFACTSPEC 1.8.0 section 7 says (R13.1).

Every case builds throwaway git repositories with a local bare remote and runs
the real command line against them. Nothing here pushes to any real remote.

The cases run against the plugin's own render_artifacts.py only (TC3: a
stand-in renderer group used to run them a second time and never caught a bug
the real one missed); the file reports a skip, with a message, while that
module is not importable.

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
    """The plugin under test and its throwaway projects."""

    def __init__(self):
        self.n = 0
        self._template = None
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
            p.ok('task-add', '--owner', 'project', '--prefix', 'DS', '--item', 'Standards',
                 '--detail', 'Keep them.', '--expected', '13 Oct', '--release')         # DS1, RELEASE-1
            p.ok('task-add', '--owner', 'artifacts', '--item', 'Spec', '--detail', 'Write it.',
                 '--expected', '10 Oct ~14:15', '--status', 'Running', '--rides', 'RELEASE-1')
            p.ok('task-add', '--owner', 'artifacts', '--item', 'Script', '--detail', 'Build it.',
                 '--expected', '11 Oct')
            p.ok('task-add', '--owner', 'site', '--item', 'Landing', '--detail', 'Ship it.',
                 '--expected', '12 Oct; with copy')
            p.ok('set-task-status', 'AR2', 'Live')
            self._template = p
        return self.project(template=self._template)


WRITING_COMMANDS = ('init', 'feature-new', 'task-add', 'set-task-status', 'edit-content', 'design', 'render',
                    'mark-published', 'mark-deferred', 'mark-deleted')


class Project:
    def __init__(self, env, name, template=None):
        self.env = env
        self.root = TMP / name
        self.bare = self.root / 'remote.git'
        self.clone = self.root / 'clone'
        self.root.mkdir(parents=True)
        if template is not None:
            shutil.copytree(str(template.bare), str(self.bare))
            git(self.root, 'clone', '-q', self.bare, self.clone)
            # the record is only ever in the working tree (AR50): copy the template's, uncommitted
            shutil.copytree(str(template.clone / 'docs'), str(self.clone / 'docs'))
            if (template.clone / '.gitignore').is_file():
                shutil.copyfile(str(template.clone / '.gitignore'), str(self.clone / '.gitignore'))
            git(self.clone, 'add', '-A')
            git(self.clone, 'commit', '-q', '-m', 'the project commits the record itself')
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
        """The record only exists in the working tree (AR50), so a fixture edits that one tree. The project
        then commits it (settled before the next command, HEAD or status read), as the owner would."""
        self._to_settle = True
        return self.clone

    _to_settle = False

    def settle(self):
        if self._to_settle:
            self._to_settle = False
            git(self.clone, 'add', '-A')
            git(self.clone, 'commit', '-q', '-m', 'the project commits a hand-edited record', check=False)

    def run(self, *args, cwd=None, env=None, push=True, rides=True):
        self.settle()
        """Run a command. Writing commands commit without pushing (R4.28); most cases read the remote
        afterwards, so they get --push unless the case passes push=False or its own --push/--no-push.
        A Running or Built task must ride a release (R5.47); to keep the cases about other things short, a case
        that gives no --rides gets the baseline release DS1 (RELEASE-1), unless it passes rides=False."""
        args = list(args)
        if rides and args and args[0] in ('task-add', 'set-task-status') and '--rides' not in args and '--release' not in args \
                and '--no-release' not in args:
            if args[0] == 'task-add':
                status = args[args.index('--status') + 1] if '--status' in args else ''
                target = None
            else:
                status = args[2] if len(args) > 2 else ''
                target = args[1] if len(args) > 1 else None
            if status.lower() in ('running', 'built', 'done') and target != 'DS1':
                args += ['--rides', 'DS1']
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
        """The file in the working tree (the record is written there and never committed, AR50)."""
        f = self.clone / path
        return f.read_text(encoding='utf-8') if f.is_file() else None

    def committed(self, path, ref='HEAD'):
        r = git(self.clone, 'show', '%s:%s' % (ref, path), check=False)
        return r.stdout if r.returncode == 0 else None

    def reg(self, ref='main'):
        return json.loads(self.show('docs/artifacts/registry.json', ref))

    def man(self, ref='main'):
        return json.loads(self.show('docs/artifacts/manifest.json', ref))

    def task(self, tid):
        return next(t for t in self.reg()['tasks'] if t['id'] == tid)

    def head(self):
        self.settle()
        return git(self.clone, 'rev-parse', 'HEAD').stdout.strip()

    @property
    def wt(self):
        return self.clone

    @property
    def old_wt(self):
        return self.clone / '.claude' / 'worktrees' / 'artifacts-record'

    @property
    def rdir(self):
        return self.clone / 'docs' / 'artifacts'

    def files(self):
        """{path: bytes} of the record in the working tree."""
        self.settle()
        return {x.relative_to(self.rdir).as_posix(): x.read_bytes() for x in self.rdir.rglob('*') if x.is_file()}

    def git_state(self):
        """HEAD, the index, the refs and the remote: what a plugin command must leave alone."""
        return (git(self.clone, 'rev-parse', 'HEAD').stdout, git(self.clone, 'ls-files', '-s').stdout,
                git(self.clone, 'for-each-ref').stdout, git(self.bare, 'for-each-ref').stdout,
                git(self.clone, 'stash', 'list').stdout)

    def record_copy(self, name):
        """A copy of the pushed record, for fixtures that damage it."""
        dest = TMP / ('rec-%s-%d' % (name, self.env.n))
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
        argv = list(argv)
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


TESTS = []          # (name, fn)


def case(fn):
    TESTS.append((fn.__name__, fn))
    return fn


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
    # the plugin writes files and stops: nothing is committed or pushed (AR50)
    assert git(p.clone, 'log', '-1', '--format=%s').stdout.strip() == 'seed'
    assert git(p.bare, 'log', '-1', '--format=%s', 'main').stdout.strip() == 'seed'
    assert 'docs/' in git(p.clone, 'status', '--porcelain').stdout
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
    assert 'docs/' in status and 'worktrees' not in status and 'artifacts-record.lock' not in status, status   # the record is left for the project to commit
    assert '.claude/artifacts-record.lock' in gi, gi
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
    # init + feature: files only, no commit
    msgs = git(p.clone, 'log', '--format=%s').stdout.split()
    assert msgs == ['seed'], msgs


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
    assert git(p.clone, 'log', '-1', '--format=%s').stdout.strip() != 'docs/artifacts: OPS1 To do'     # never committed
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
def test_set_task_status_item_corrects_title(env):
    p = env.baseline()
    old = p.task('AR1')['item']
    p.ok('set-task-status', 'AR1', 'Running', '--item', '  A   corrected title ')
    assert p.task('AR1')['item'] == 'A corrected title'
    hist = json.loads(p.show('docs/artifacts/content/artifacts/history.json'))
    assert hist[0]['change'] == 'AR1 item changed from "%s" to "A corrected title"' % old, hist[0]
    assert p.run('check').code == 0
    for bad, text in (('x' * 81, '80'), ('  ', 'empty')):
        r = p.run('set-task-status', 'AR1', 'Running', '--item', bad)
        assert r.code == 1 and text in r.err, r.all
    assert p.task('AR1')['item'] == 'A corrected title'


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
    files = p.files()
    for argv in (['task-add', '--owner', 'artifacts', '--item', 'x', '--detail', 'd', '--expected', '14 Oct'],
                 ['set-task-status', 'AR1', 'Running']):
        r = p.run(*argv, '--basis', 'b' * 81)
        assert r.code == 1 and '80' in r.err, r.all
    assert p.files() == files, 'the refused calls wrote nothing'
    assert p.run('set-task-status', 'AR1', 'Running', '--basis', 'b' * 80).code == 0
    assert p.files() != files and p.head() == before


@case
def test_release_flags_store_the_fields(env):
    """R5.40: --release, --phase, --risk and --rides are stored as optional fields, and cleared with ""."""
    p = env.baseline()
    r = p.ok('task-add', '--owner', 'project', '--item', 'DL12 release', '--detail', 'Join, CI, merge.',
             '--expected', '10 Oct ~18:00', '--release',
             '--phase', 'agents=17:30-17:45', '--phase', 'join=17:45-17:48', '--phase', 'ci=17:48-17:54',
             '--phase', 'merge=17:54-18:00', '--risk', '+1 fix round=10')
    rel = r.out.strip()
    t = p.task(rel)
    assert t['release'] == 2 and t['risk'] == {'label': '+1 fix round', 'minutes': 10}, t
    assert [(x['name'], x['start'], x['end']) for x in t['phases']] == [
        ('agents', '2026-10-10T17:30+01:00', '2026-10-10T17:45+01:00'),
        ('join', '2026-10-10T17:45+01:00', '2026-10-10T17:48+01:00'),
        ('ci', '2026-10-10T17:48+01:00', '2026-10-10T17:54+01:00'),
        ('merge', '2026-10-10T17:54+01:00', '2026-10-10T18:00+01:00')], t['phases']
    assert 'release' not in p.task('AR1') and 'phases' not in p.task('AR1'), 'no flags, no fields'
    # a task that rides the release, and the timeline in the rendered Full Progress
    p.ok('set-task-status', 'AR1', 'Running', '--rides', rel)
    assert p.task('AR1')['rides'] == rel
    fp = p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file']) or ''
    assert 'class="release-timeline"' in fp and 'live ~18:00' in fp and 'worst ~18:10' in fp and 'data-col="state"' in fp
    # the explicit date form, a replaced phase list and the clearing forms
    p.ok('set-task-status', rel, 'Running', '--phase', 'agents=10 Oct 17:30-10 Oct 18:00')
    assert p.task(rel)['phases'][0]['name'] == 'agents' and len(p.task(rel)['phases']) == 1
    p.ok('set-task-status', rel, 'Running', '--phase', '', '--risk', '', '--rides', '')
    t = p.task(rel)
    assert 'phases' not in t and 'risk' not in t and t['release'] == 2, t
    p.ok('set-task-status', 'AR1', 'Waiting', '--rides', '')
    assert 'rides' not in p.task('AR1')
    assert p.run('check').code == 0


@case
def test_release_expected_is_the_end_of_the_last_phase(env):
    """R5.41: an open release's Expected must be the end of its last phase; a mismatch is refused, nothing written."""
    p = env.baseline()
    before = p.head()
    r = p.run('task-add', '--owner', 'project', '--item', 'R', '--detail', 'd', '--expected', '10 Oct ~18:10', '--release',
              '--phase', 'agents=17:30-17:45', '--phase', 'merge=17:54-18:00')
    assert r.code == 1 and '~18:00' in r.err and 'last phase' in r.err, r.all
    assert p.head() == before
    ok = p.ok('task-add', '--owner', 'project', '--item', 'R', '--detail', 'd', '--expected', '10 Oct ~18:00; fix round named',
              '--release', '--phase', 'agents=17:30-17:45', '--phase', 'merge=17:54-18:00')
    rel = ok.out.strip()
    # moving the Expected away from the phases is refused too, and so is a phase change that leaves it behind
    r = p.run('set-task-status', rel, 'Running', '--expected', '10 Oct ~19:00')
    assert r.code == 1 and 'last phase' in r.err, r.all
    r = p.run('set-task-status', rel, 'Running', '--phase', 'agents=17:30-18:20')
    assert r.code == 1 and '~18:20' in r.err, r.all
    p.ok('set-task-status', rel, 'Running', '--phase', 'agents=17:30-18:20', '--expected', '10 Oct ~18:20')
    # a closed release is not held to it (Expected is then the date it happened)
    p.ok('set-task-status', rel, 'Live')
    assert p.task(rel)['expected'] == '10 Oct' and p.run('check').code == 0


@case
def test_release_refusals(env):
    """R5.40: --rides must name a release; phases and risk need --release; bad phases and risks are refused."""
    p = env.baseline()
    before = p.head()
    add = ['task-add', '--owner', 'project', '--item', 'R', '--detail', 'd', '--expected', '10 Oct ~18:00']
    bad = [
        (add + ['--rides', 'AR1'], 'not a release'),
        (add + ['--rides', 'ZZ9'], 'not a task'),
        (add + ['--phase', 'agents=17:30-18:00'], '--release'),
        (add + ['--risk', 'x=5'], '--release'),
        (add + ['--release', '--phase', 'deploy=17:30-18:00'], 'one of agents, join, ci, merge'),
        (add + ['--release', '--phase', 'agents=18:00-17:30'], 'after the start'),
        (add + ['--release', '--phase', 'agents=17:30-17:45', '--phase', 'agents=17:45-18:00'], 'twice'),
        (add + ['--release', '--phase', 'agents=17:30'], 'NAME=HH:MM-HH:MM'),
        (add + ['--release', '--phase', 'agents=25:00-26:00'], 'HH:MM'),
        (add + ['--release', '--phase', '', '--phase', 'agents=17:30-18:00'], 'alone'),
        (add + ['--release', '--risk', 'no minutes'], 'LABEL=MINUTES'),
        (add + ['--release', '--risk', 'zero=0'], 'LABEL=MINUTES'),
        (add + ['--release', '--risk', ('x' * 41) + '=5'], 'at most 40'),
        (['set-task-status', 'AR1', 'Running', '--rides', 'AR2'], 'not a release'),
        (['set-task-status', 'AR1', 'Running', '--phase', 'agents=17:30-18:00'], '--release'),
    ]
    for argv, word in bad:
        r = p.run(*argv)
        assert r.code == 1 and word in r.err, (argv, r.all)
    assert p.head() == before, 'a refused change writes nothing'


@case
def test_release_numbers_are_assigned_and_never_reused(env):
    """R5.45: --release gives the next number (highest + 1), keeps an existing one, and a number is never reused."""
    p = env.baseline()
    assert p.task('DS1')['release'] == 1
    r = p.ok('task-add', '--owner', 'project', '--item', 'Second', '--detail', 'd', '--expected', '14 Oct', '--release')
    second = r.out.strip()
    assert p.task(second)['release'] == 2
    p.ok('set-task-status', second, 'Running', '--release')                 # an existing number is left alone
    assert p.task(second)['release'] == 2
    # a Live release keeps its number, and the next one is the highest plus one
    p.ok('set-task-status', second, 'Live')
    r = p.ok('task-add', '--owner', 'project', '--item', 'Third', '--detail', 'd', '--expected', '15 Oct', '--release')
    assert p.task(r.out.strip())['release'] == 3
    # --release on an existing plain task numbers it too
    p.ok('set-task-status', 'SI1', 'To do', '--release')
    assert p.task('SI1')['release'] == 4
    fp = p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    assert '<span class="release-name">RELEASE-4</span>' in fp
    assert p.run('check').code == 0


@case
def test_rides_accepts_the_release_name(env):
    """R5.45: --rides takes RELEASE-<n> and stores the release's task ID; an unknown number is refused."""
    p = env.baseline()
    p.ok('set-task-status', 'SI1', 'Running', '--rides', 'RELEASE-1')
    assert p.task('SI1')['rides'] == 'DS1', p.task('SI1')
    before = p.head()
    r = p.run('set-task-status', 'SI1', 'Running', '--rides', 'RELEASE-9')
    assert r.code == 1 and 'RELEASE-9' in r.err and p.head() == before, r.all


@case
def test_migration_numbers_old_releases(env):
    """R5.45: rows that say "release": true are numbered by the migration, oldest changed first, ties by ID."""
    p = env.baseline()
    other = p.clone_again('old-releases')
    rp = other / 'docs' / 'artifacts' / 'registry.json'
    reg = json.loads(rp.read_text(encoding='utf-8'))
    for t in reg['tasks']:
        if t['id'] == 'DS1':
            t['release'] = True
            t['changed'] = '2026-10-09T10:00+01:00'
    for i, when in enumerate(['2026-10-08T10:00+01:00', '2026-10-09T10:00+01:00']):
        reg['tasks'].append({'id': 'DS%d' % (i + 2), 'owner': 'project', 'app': '', 'status': 'Live', 'item': 'old %d' % i,
                             'detail': 'd', 'expected': '08 Oct', 'changed': when, 'release': True})
    rp.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    out = p.run('check', '--json').json()
    assert any('DS1' in n and 'release' in n for n in out['notes']), out
    p.ok('render')
    nums = {t['id']: t.get('release') for t in p.reg()['tasks'] if 'release' in t}
    assert nums == {'DS2': 1, 'DS1': 2, 'DS3': 3}, nums           # oldest first; DS1 and DS3 tie, DS1 first
    assert p.run('check').code == 0, p.run('check').all


@case
def test_running_and_built_must_ride_a_release(env):
    """R5.47: Running and Built tasks (not releases) need --rides; refused otherwise; old findings do not freeze."""
    p = env.baseline()
    before = p.head()
    for argv in (['task-add', '--owner', 'site', '--item', 'x', '--detail', 'd', '--expected', '14 Oct', '--status', 'Running'],
                 ['set-task-status', 'SI1', 'Running'], ['set-task-status', 'SI1', 'Built']):
        r = p.run(*argv, rides=False)
        assert r.code == 1 and '--rides' in r.err, (argv, r.all)
    assert p.head() == before
    p.ok('set-task-status', 'SI1', 'Built', '--rides', 'DS1')
    p.ok('task-add', '--owner', 'project', '--item', 'a release', '--detail', 'd', '--expected', '14 Oct',
         '--status', 'Running', '--release')                          # a release itself needs no release
    # an older record with a Running task riding nothing: check reports it, other changes still go through
    other = p.clone_again('no-rides')
    rp = other / 'docs' / 'artifacts' / 'registry.json'
    reg = json.loads(rp.read_text(encoding='utf-8'))
    next(t for t in reg['tasks'] if t['id'] == 'AR1').pop('rides')
    rp.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    assert 'R5.47' in p.run('check').out
    p.ok('set-task-status', 'AR2', 'Live', '--detail', 'still works')


@case
def test_no_release_tasks_may_run_without_a_release(env):
    """R5.47a: --no-release REASON on task-add and set-task-status; the task may be Running (or any open status) with
    no release, goes Live when finished, shows `ships nothing` in Full Progress, and check is clean."""
    p = env.baseline()
    p.ok('task-add', '--owner', 'artifacts', '--item', 'Publish limit study', '--detail', 'Read only.',
         '--expected', '14 Oct', '--status', 'Running', '--no-release', 'a study, nothing to ship')
    assert p.task('AR3')['no_release'] == 'a study, nothing to ship' and 'rides' not in p.task('AR3')
    for status in ('Waiting', 'Needs you', 'To do', 'Running'):
        p.ok('set-task-status', 'AR3', status, rides=False)
        assert p.task('AR3')['no_release'] == 'a study, nothing to ship'
    fp = p.man()['full_progress_artifact']['file']
    page = p.show('docs/artifacts/' + fp)
    row = page[page.index('<tr data-task="AR3">'):]
    assert '<span class="no-release-line">ships nothing: a study, nothing to ship</span>' in row[:row.index('</tr>')]
    assert 'Not in a release yet' in page[:page.index('<tr data-task="AR3">')]
    assert p.run('check').code == 0, p.run('check').all
    p.ok('set-task-status', 'AR3', 'Live', rides=False)
    assert p.task('AR3')['status'] == 'Live' and p.run('check').code == 0
    # a task that was set Running by hand without a release is still refused once the reason is cleared
    p.ok('set-task-status', 'AR3', 'Waiting', '--no-release', '', rides=False)
    assert 'no_release' not in p.task('AR3')
    r = p.run('set-task-status', 'AR3', 'Running', rides=False)
    assert r.code == 1 and '--rides' in r.err and '--no-release' in r.err, r.all
    p.ok('set-task-status', 'AR3', 'Running', '--no-release', 'a cleanup')
    assert p.task('AR3')['no_release'] == 'a cleanup'


@case
def test_no_release_refusals(env):
    """R5.47a: --no-release is refused with --release or --rides, over 80 characters, on a task that rides, and
    Built on a task that carries it; check reports a record that breaks the rule."""
    p = env.baseline()
    before = p.head()
    p.ok('task-add', '--owner', 'site', '--item', 'x', '--detail', 'd', '--expected', '14 Oct', '--no-release', 'nothing')
    before = p.head()
    for argv, word in ((['task-add', '--owner', 'site', '--item', 'x', '--detail', 'd', '--expected', '14 Oct',
                         '--no-release', 'r', '--release'], '--release'),
                       (['task-add', '--owner', 'site', '--item', 'x', '--detail', 'd', '--expected', '14 Oct',
                         '--no-release', 'r', '--rides', 'RELEASE-1'], '--rides'),
                       (['set-task-status', 'SI2', 'Waiting', '--no-release', 'r', '--release'], '--release'),
                       (['set-task-status', 'SI2', 'Waiting', '--no-release', 'r', '--rides', 'DS1'], '--rides'),
                       (['set-task-status', 'SI2', 'Waiting', '--no-release', 'x' * 81], '80'),
                       (['set-task-status', 'SI2', 'Built'], 'never Built'),
                       (['set-task-status', 'AR1', 'Waiting', '--no-release', 'it rides'], 'rides none')):
        r = p.run(*argv, rides=False)
        assert r.code == 1 and word in r.err, (argv, r.all)
    assert p.head() == before
    p.ok('set-task-status', 'SI2', 'Waiting', '--no-release', 'x' * 80, rides=False)
    # check reports a record that carries both, or a Built task that ships nothing
    for name, edit in (('both', lambda t: t.update({'rides': 'DS1'})), ('built', lambda t: t.update({'status': 'Built', 'expected': '10 Oct'})),
                       ('empty', lambda t: t.update({'no_release': ''})), ('long', lambda t: t.update({'no_release': 'y' * 81}))):
        d = p.record_copy('nr-' + name)
        rp = d / 'registry.json'
        reg = json.loads(rp.read_text(encoding='utf-8'))
        edit(next(t for t in reg['tasks'] if t['id'] == 'SI2'))
        rp.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
        r = check_record(env, d)
        assert 'R5.47a' in r.out, (name, r.all)


@case
def test_state_column_counts_in_the_record(env):
    """R5.44: Full Progress's State shows Complete for a finished feature and counts per open status otherwise."""
    p = env.baseline()
    fp = p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    assert fp is not None
    import re
    rows = re.findall(r'<tr><td data-value="[^"]*">.*?</tr>', fp, re.S)
    cell = lambda row: re.search(r'<td data-col="state">(.*?)</td>', row, re.S).group(1)
    states = [re.sub(r'<[^>]+>', ' ', cell(r)).split() for r in rows]
    by_title = {re.search(r'Feature: ([^<]+)<', r).group(1): s for r, s in zip(rows, states)}
    assert by_title['Artifacts'] == ['1', 'Running'], by_title
    p.ok('set-task-status', 'SI1', 'Live')
    fp = p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    rows = re.findall(r'<tr><td data-value="[^"]*">.*?</tr>', fp, re.S)
    site = next(r for r in rows if 'The site' in r)
    assert 'Complete' in cell(site) and 'status-live' in cell(site)
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

def dirty_outside(p):
    """Changes anywhere but docs/artifacts/ (the record's own files are meant to change)."""
    return [x for x in dirty(p) if not x[3:].startswith('docs/artifacts/')]


def dirty(p):
    p.settle()
    return [x for x in git(p.wt, 'status', '--porcelain').stdout.splitlines() if x.strip()]


def export(p, key, name):
    dest = TMP / ('exp-%s-%d' % (name, p.env.n))
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
    r = p.ok('export-content', 'full-progress', '--to', TMP / ('exp-fp-%d' % (env.n)), '--json')
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
    assert p.run('check').code == 0
    assert dirty_outside(p) == [] and p.head() == p.head(), dirty(p)       # only docs/artifacts/ changed, nothing committed
    assert any(x.endswith('feature-artifacts.html') for x in dirty(p))


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
    empty = TMP / ('empty-%d' % (env.n))
    env.n += 1
    empty.mkdir()
    r = p.run('edit-content', 'artifacts', '--from', empty)
    assert r.code == 1 and p.head() == before
    assert p.show('docs/artifacts/content/artifacts/meta.json') is not None


@case
def test_render_noop_and_all(env):
    p = env.baseline()
    before = p.head()
    files = p.files()
    r = p.ok('render')
    assert 'nothing to do' in r.out and p.head() == before and p.files() == files
    r = p.ok('render', '--all', '--json', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-11T08:00:00+00:00'})
    assert sorted(r.json()['rendered']) == sorted(['full-progress', 'artifacts', 'site'])
    assert p.files() != files and p.head() == before
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


def _publish_full_progress(p, **kw):
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/ccc', **kw)
    assert p.run('pending', '--json').json() == {'artifacts': [], 'queue': [], 'retired': []}


@case
def test_detail_only_change_needs_no_publish(env):
    """R9.6: a change to a detail, a basis or a content section is committed and rendered, but pending stays empty;
    a record with no stored fingerprint needs one publish."""
    p = env.baseline()
    _publish_full_progress(p)
    assert len(p.man()['full_progress_artifact']['published_fingerprint']) == 64
    fp_file = p.man()['full_progress_artifact']['file']
    page = p.show('docs/artifacts/' + fp_file)
    p.ok('set-task-status', 'AR1', 'Running', '--detail', 'Now it is written differently.')
    p.ok('set-task-status', 'AR1', 'Running', '--basis', 'waits on a review, 10 min')
    assert p.show('docs/artifacts/' + fp_file) != page, 'the new detail is rendered and committed'
    r = p.run('pending', '--json')
    assert r.code == 0 and r.json() == {'artifacts': [], 'queue': [], 'retired': []}, r.all
    assert p.run('pending').out.strip() == 'nothing pending'
    assert p.run('check').code == 0
    # it rides the next publish: a status change lists Full Progress, and publishing ends it
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert [a['key'] for a in p.run('pending', '--json').json()['artifacts']] == ['full-progress']
    _publish_full_progress(p)
    # an older record has no fingerprint: one publish is needed, then it is recorded
    other = p.clone_again('no-fingerprint')
    mp = other / 'docs' / 'artifacts' / 'manifest.json'
    man = json.loads(mp.read_text(encoding='utf-8'))
    man['full_progress_artifact'].pop('published_fingerprint')
    mp.write_text(json.dumps(man, indent=2) + '\n', encoding='utf-8')
    p.ok('set-task-status', 'AR1', 'Waiting', '--detail', 'only a detail')
    again = p.run('pending', '--json')
    assert again.code == 1 and again.json()['artifacts'][0]['reason'] == 'changed since last publish', again.all
    _publish_full_progress(p)
    assert 'published_fingerprint' in p.man()['full_progress_artifact']


@case
def test_status_change_needs_a_publish(env):
    """R9.6: a task added, or a task's status, item, Expected or release fields change what the owner sees."""
    p = env.baseline()
    _publish_full_progress(p)
    steps = (
        ('status', ['set-task-status', 'AR1', 'Waiting']),
        ('added', ['task-add', '--owner', 'site', '--item', 'New', '--detail', 'd', '--expected', '15 Oct']),
        ('expected', ['set-task-status', 'SI1', 'To do', '--expected', '16 Oct']),
        ('rides', ['set-task-status', 'AR1', 'Waiting', '--rides', '']),
        ('no_release', ['set-task-status', 'AR1', 'Waiting', '--no-release', 'a study']),
        ('release', ['set-task-status', 'DS1', 'Running', '--risk', '+1 round=10']),
    )
    for name, argv in steps:
        p.ok(*argv, rides=False)
        r = p.run('pending', '--json')
        assert r.code == 1 and [a['key'] for a in r.json()['artifacts']] == ['full-progress'], (name, r.all)
        _publish_full_progress(p)
    # the same Expected with a new detail changes nothing the owner sees
    p.ok('set-task-status', 'SI1', 'To do', '--detail', 'same', '--expected', '16 Oct')
    assert p.run('pending').code == 0


@case
def test_deferred_publish_does_not_block_until_the_reset(env):
    """R9.7: mark-deferred full-progress --until <ISO>: until then pending lists it as deferred and exits 0; after
    that time it lists it as before; mark-published clears the deferral."""
    p = env.baseline()
    _publish_full_progress(p)
    p.ok('set-task-status', 'AR1', 'Waiting')
    assert p.run('pending').code == 1
    until = '2026-10-11T01:00:00+01:00'
    p.ok('mark-deferred', 'full-progress', '--until', until)
    assert p.man()['full_progress_artifact']['deferred_until'] == '2026-10-11T01:00+01:00'
    r = p.run('pending')
    assert r.code == 0 and 'deferred full-progress' in r.out and 'deferred until 01:00 (Lisbon)' in r.out, r.all
    assert 'publish full-progress' not in r.out
    j = p.run('pending', '--json')
    assert j.code == 0 and j.json()['artifacts'] == [] and j.json()['deferred'][0]['key'] == 'full-progress', j.all
    assert j.json()['deferred'][0]['reason'] == 'deferred until 01:00 (Lisbon)'
    assert p.run('check').code == 0
    # after the reset both behave as before
    late = {'CLAUDE_ARTIFACTS_NOW': '2026-10-11T01:30:00+01:00'}
    r = p.run('pending', '--json', env=late)
    assert r.code == 1 and [a['key'] for a in r.json()['artifacts']] == ['full-progress'] and 'deferred' not in r.json(), r.all
    # a later publish clears the deferral
    p.ok('mark-deferred', 'full-progress', '--until', '2026-10-12T00:00:00+00:00')
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/ccc')
    assert 'deferred_until' not in p.man()['full_progress_artifact']
    assert p.run('pending', '--json').json() == {'artifacts': [], 'queue': [], 'retired': []}
    # refusals: a past time, a bad time, a feature artifact, an unknown key
    before = p.head()
    for argv, word in ((['mark-deferred', 'full-progress', '--until', '2026-10-10T10:00:00+00:00'], 'future'),
                       (['mark-deferred', 'full-progress', '--until', 'tomorrow'], 'ISO'),
                       (['mark-deferred', 'full-progress', '--until', '2026-10-12T00:00:00'], 'ISO'),
                       (['mark-deferred', 'artifacts', '--until', until], 'feature artifact'),
                       (['mark-deferred', 'ghost', '--until', until], 'unknown artifact key')):
        r = p.run(*argv)
        assert r.code == 1 and word in r.err, (argv, r.all)
    assert p.head() == before


def _stamp_of(text):
    return re.search(r'<time datetime="([^"]+)"', text).group(1)


def _fp_row_time(fp_html, title):
    """The ISO time Full Progress section 1 shows for a feature."""
    m = re.search(r'<td data-value="[^"]*"><a href="[^"]*">%s</a></td><td data-value="\d+"><time datetime="([^"]+)"' % re.escape(title), fp_html)
    return m.group(1) if m else None


@case
def test_feature_updated_and_published_line(env):
    """R4.30, R5.6, R5.38: `updated` follows the page's stamp, Full Progress shows it and is rendered after the features."""
    p = env.baseline()
    m = p.man()
    arts = next(e for e in m['feature_artifacts'] if e['key'] == 'artifacts')
    site = next(e for e in m['feature_artifacts'] if e['key'] == 'site')
    fp = m['full_progress_artifact']
    later = '2026-10-11T09:00:00+01:00'
    p.ok('set-task-status', 'AR1', 'Waiting', env={'CLAUDE_ARTIFACTS_NOW': later})
    m = p.man()
    arts2 = next(e for e in m['feature_artifacts'] if e['key'] == 'artifacts')
    site2 = next(e for e in m['feature_artifacts'] if e['key'] == 'site')
    page = p.show('docs/artifacts/' + arts['file'])
    assert arts2['updated'] == _stamp_of(page) and arts2['updated'] != arts.get('updated')      # the page's own stamp
    assert site2.get('updated') == site.get('updated')                                          # untouched pages keep theirs
    fp_html = p.show('docs/artifacts/' + fp['file'])
    assert _fp_row_time(fp_html, 'Feature: Artifacts') == arts2['updated']                      # section 1 shows it (INV-3 holds: check is clean)
    assert _fp_row_time(fp_html, 'Feature: The site') == _stamp_of(p.show('docs/artifacts/' + site['file']))
    # newest first: the page that just changed is on top
    assert fp_html.index('Feature: Artifacts</a>') < fp_html.index('Feature: The site</a>')
    assert 'full-progress-published' not in page.split('</style>')[-1]                         # nothing published yet
    assert p.run('check').code == 0
    # an older record without `updated` is read from the feature file, and rewritten at the next change
    d = p.record_copy('noupdated')
    man = json.loads((d / 'manifest.json').read_text(encoding='utf-8'))
    for e in man['feature_artifacts']:
        e.pop('updated', None)
    (d / 'manifest.json').write_text(json.dumps(man, indent=1), encoding='utf-8')
    assert check_record(env, d).code == 0, check_record(env, d).all
    man['feature_artifacts'][0]['updated'] = 'yesterday'
    (d / 'manifest.json').write_text(json.dumps(man, indent=1), encoding='utf-8')
    r = check_record(env, d)
    assert r.code == 1 and 'R4.30' in r.out, r.all


@case
def test_publish_does_not_loop(env):
    """R5.38: recording a publish puts the line on the feature pages without moving their stamps, so Full
    Progress does not change and `pending` has nothing to list, again and again."""
    p = env.baseline()
    m = p.man()
    files = {e['key']: e['file'] for e in m['feature_artifacts']}
    fp_file = m['full_progress_artifact']['file']
    before = {k: p.show('docs/artifacts/' + f) for k, f in files.items()}
    fp_before = p.show('docs/artifacts/' + fp_file)
    at = '2026-10-12T10:30:00+01:00'
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/one', env={'CLAUDE_ARTIFACTS_NOW': at})
    m = p.man()
    assert m['full_progress_artifact']['published_at'] == '2026-10-12T10:30+01:00'
    assert p.run('pending', '--json').json() == {'artifacts': [], 'queue': [], 'retired': []}      # nothing to publish again
    assert p.show('docs/artifacts/' + fp_file) == fp_before                                        # Full Progress did not change
    for key, f in files.items():
        page = p.show('docs/artifacts/' + f)
        assert '<a href="https://claude.ai/artifact/one">12 Oct 10:30</a> (Lisbon)' in page and 'Full Progress published: ' in page
        assert _stamp_of(page) == _stamp_of(before[key])                                           # the stamp did not move
        assert page.replace(re.search(r'<p class="full-progress-published">.*?</p>\n', page).group(0), '') == before[key]
        e = next(x for x in m['feature_artifacts'] if x['key'] == key)
        assert e.get('updated') == next(x for x in p.man('main~1')['feature_artifacts'] if x['key'] == key).get('updated')
    assert p.run('check').code == 0
    # a second publish with a new URL: the links move, the stamps and Full Progress do not, pending stays empty
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/two', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-12T11:45:00+01:00'})
    assert p.run('pending', '--json').json() == {'artifacts': [], 'queue': [], 'retired': []}
    assert p.show('docs/artifacts/' + fp_file) == fp_before
    for key, f in files.items():
        page = p.show('docs/artifacts/' + f)
        assert '<a href="https://claude.ai/artifact/two">12 Oct 11:45</a>' in page and '/one' not in page
        assert _stamp_of(page) == _stamp_of(before[key])
    assert p.run('check').code == 0
    # and a real change still lists Full Progress once, and publishing it again ends there
    p.ok('set-task-status', 'AR1', 'Waiting', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-13T08:00:00+01:00'})
    assert [a['key'] for a in p.run('pending', '--json').json()['artifacts']] == ['full-progress']
    p.ok('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/two', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-13T08:05:00+01:00'})
    assert p.run('pending', '--json').json() == {'artifacts': [], 'queue': [], 'retired': []}
    page = p.show('docs/artifacts/' + files['artifacts'])
    assert '13 Oct 08:05' in page and _stamp_of(page).startswith('2026-10-13T08:00')               # the line follows the publish, the stamp the change
    assert p.run('check').code == 0


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
    """R5.30, R5.31: relative links in the committed file, a Copy link button with the absolute file:/// address in the copy."""
    p = env.baseline()
    a = p.run('pending', '--json').json()['artifacts'][0]
    copy = Path(a['path']).read_text(encoding='utf-8')
    committed = p.show('docs/artifacts/' + a['file'])
    # committed: relative file names only
    assert 'href="feature-artifacts.html"' in committed and 'href="feature-the-site.html"' in committed
    assert 'href="file:' not in committed and 'class="local-path"' not in committed and 'copy-link"' not in committed and 'data-copy="' not in committed
    # the copy: one button per feature in section 1 holds the absolute file:/// address; no anchor, rows carry no link
    hrefs = re.findall(r'class="copy-link" data-copy="(file:///[^"]+)"', copy)
    assert sorted(h.rsplit('/', 1)[1] for h in hrefs) == ['feature-artifacts.html', 'feature-the-site.html'], hrefs
    assert copy.count('class="copy-link"') == 2 and 'href="file:' not in copy and 'href="feature-' not in copy
    for h in hrefs:
        target = Path(url_path(h))
        assert target.is_absolute() and target.is_file() and target.parent.name == 'artifacts'
        assert os.path.samefile(str(target), str(p.rdir / target.name)), (h, target)   # docs/artifacts/ of the working tree
        assert '<code class="local-path" hidden>%s</code>' % h in copy
    # the checklist rows (AR1, AR2, SI1) carry no link and no button
    table = copy[copy.index('<table class="status-checklist"'):]
    table = table[:table.index('</table>')]
    assert '<a ' not in table and 'copy-link' not in table and 'file:///' not in table
    # the copy is outside the record and ignored once .gitignore says so (R10.2)
    (p.clone / '.gitignore').write_text('', encoding='utf-8')
    assert 'does not ignore' in p.run('pending').err
    (p.clone / '.gitignore').write_text('.claude/artifacts-publish/\n', encoding='utf-8')
    assert 'does not ignore' not in p.run('pending').err
    assert 'artifacts-publish' not in git(p.clone, 'status', '--porcelain', '--untracked-files=all').stdout


@case
def test_publish_copy_path_encoding_with_spaces(env):
    """R5.31: a space in the path is %20 in the URL and a plain space in the text; `&` is %26 / &amp;."""
    env.baseline()
    q = Project(env, 'a b&c %d' % env.n, env._template)
    a = q.run('pending', '--json').json()['artifacts'][0]
    copy = Path(a['path']).read_text(encoding='utf-8')
    hrefs = sorted(set(re.findall(r'data-copy="(file:///[^"]+)"', copy)))
    assert 'href="file:' not in copy
    assert len(hrefs) == 2 and all('%20' in h and ' ' not in h and '%26' in h and '&' not in h for h in hrefs), hrefs
    for h in hrefs:
        assert os.path.samefile(url_path(h), str(q.rdir / h.rsplit('/', 1)[1])), h
        assert '\\' not in h                                              # forward slashes only
    assert re.search(r'title="[^"]*a b&amp;c[^"]*feature-artifacts\.html"', copy), 'path text keeps the space'
    assert q.run('check').code == 0


@case
def test_old_feature_urls_migrate(env):
    """R4.18: a manifest whose feature entries hold a url or a hash is read without them, noted by check,
    rewritten by the next writing command, and its feature pages and Full Progress links are rendered again."""
    p = env.baseline()
    other = p.clone_again('legacy')
    f = other / 'docs' / 'artifacts' / 'manifest.json'
    edit_json(f, lambda m: (feat(m).update(url='https://claude.ai/artifact/old-a', published_sha256='a' * 64),
                            feat(m, 'site').update(url='https://claude.ai/artifact/old-b')))
    page = other / 'docs' / 'artifacts' / 'feature-artifacts.html'
    page.write_text('<title>Feature: Artifacts</title>\n<time datetime="2026-10-10T12:39+01:00">x</time>\n', encoding='utf-8')
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
    files = p.files()
    r = p.ok('edit-content', 'artifacts', '--from', d)
    assert 'no change' in r.out, r.out
    assert p.head() == before and p.files() == files, 'nothing written'
    assert p.ok('edit-content', 'artifacts', '--from', d, '--json').json()['changed'] is False
    # CRLF copies of the same files are the same content
    for f in d.iterdir():
        f.write_bytes(f.read_bytes().replace(b'\n', b'\r\n'))
    assert 'no change' in p.ok('edit-content', 'artifacts', '--from', d).out and p.head() == before
    (d / 'meta.json').write_text((d / 'meta.json').read_text(encoding='utf-8').replace('Planned', 'Planned,'), encoding='utf-8')
    p.ok('edit-content', 'artifacts', '--from', d)
    assert p.files() != files and p.head() == before


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
    d = TMP / ('wt-%s-%d' % (name, env.n))
    env.n += 1
    return d


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
    ('release false', 'R5.45', lambda r: task(r, 'AR1').update(release=False)),
    ('release zero', 'R5.45', lambda r: task(r, 'AR1').update(release=0)),
    ('release repeated', 'R5.45', lambda r: task(r, 'AR1').update(release=1)),
    ('running task rides nothing', 'R5.47', lambda r: task(r, 'AR1').pop('rides')),
    ('built task rides nothing', 'R5.47', lambda r: task(r, 'SI1').update(status='Built', expected='10 Oct')),
    ('phases on a non-release', 'R5.40', lambda r: task(r, 'AR1').update(phases=[{'name': 'agents', 'start': '2026-10-10T17:30+01:00', 'end': '2026-10-10T17:45+01:00'}])),
    ('bad phase name', 'R5.40', lambda r: task(r, 'AR1').update(release=5, phases=[{'name': 'deploy', 'start': '2026-10-10T17:30+01:00', 'end': '2026-10-10T17:45+01:00'}])),
    ('phase ends before it starts', 'R5.40', lambda r: task(r, 'AR1').update(release=5, phases=[{'name': 'ci', 'start': '2026-10-10T17:45+01:00', 'end': '2026-10-10T17:30+01:00'}])),
    ('bad risk', 'R5.40', lambda r: task(r, 'AR1').update(release=5, risk={'label': '', 'minutes': 0})),
    ('rides a non-release', 'R5.40', lambda r: task(r, 'SI1').update(rides='AR2')),
    ('rides an unknown task', 'R5.40', lambda r: task(r, 'SI1').update(rides='ZZ9')),
    ('expected is not the end of the last phase', 'R5.41', lambda r: task(r, 'AR1').update(release=5, expected='10 Oct ~19:00', phases=[{'name': 'agents', 'start': '2026-10-10T17:30+01:00', 'end': '2026-10-10T17:45+01:00'}])),
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
    next(t for t in reg['tasks'] if t['id'] == 'AR2').update(status='Done', rides='DS1')
    rp.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
    man = json.loads(mp.read_text(encoding='utf-8'))
    man['merged_status'] = 'Done'
    mp.write_text(json.dumps(man, indent=2) + '\n', encoding='utf-8')
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
        d = TMP / ('fx-%d' % (n))
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


@case
def test_check_runs_check_html(env):
    p = env.baseline()
    rec = p.record_copy('html')
    f = rec / 'feature-the-site.html'
    text = f.read_text(encoding='utf-8')
    assert '<title>Feature: ' in text
    f.write_text(text.replace('<title>Feature: ', '<title>Wrong: ', 1), encoding='utf-8')
    r = check_record(env, rec)
    assert r.code == 1 and has_line(r.out, 'R5.1', 'feature-the-site.html'), r.all
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


def hand_decisions_sections(p, keys, tag='hand-d'):
    """Push to main a hand-written section titled Decisions in each of the features (R5.19), as a 1.0.0 record can have."""
    other = p.clone_again(tag)
    for key in keys:
        d = other / 'docs' / 'artifacts' / 'content' / key
        n = len(list(d.glob('[0-9][0-9]-*.html'))) + 1
        (d / ('%02d-decisions.html' % n)).write_text('<!-- title: Decisions -->\n<p>By hand.</p>\n', encoding='utf-8')


@case
def test_earlier_findings_do_not_block_a_change(env):
    """R7.1: a writing command may leave the findings the record already had; it says so and writes the change."""
    p = env.baseline()
    hand_break_registry(p)
    before = p.head()
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R6.6'), r.all
    r = p.ok('set-task-status', 'SI1', 'Waiting')
    assert p.task('SI1')['status'] == 'Waiting' and dirty(p)
    assert re.search(r'note: \d earlier findings? remains?; run check', r.out), r.all
    r = p.run('check')
    assert r.code == 1 and has_line(r.out, 'R6.6'), r.all
    # the fixing command is allowed, and ends the finding
    r = p.ok('set-task-status', 'AR1', 'Waiting', '--expected', '14 Oct')
    assert 'earlier finding' not in r.all
    assert p.run('check').code == 0
    assert dirty_outside(p) == []


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
    dirty_before, files_before = dirty(p), p.files()
    r = p.run('set-task-status', 'AR1', 'Waiting')
    assert r.code == 1 and 'content/artifacts is invalid; fix it with edit-content' in r.err, r.all
    assert has_line(r.err, 'R5.19', 'content/artifacts') and p.head() == before and dirty(p) == dirty_before
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
    assert dirty_outside(p) == []


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
    edit_json(rp, lambda r: task(r, 'AR2').update(status='Done', rides='DS1'))
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
    assert p.show('docs/artifacts/feature-the-site.html') == site_html and p.head() == before
    r = p.ok('render')
    assert 'nothing to do' in r.out and 'note: 1 earlier finding remains; run check' in r.out, r.all
    assert dirty_outside(p) == []


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
    """A token block that satisfies the renderer's token contract."""
    base = (REAL_PLUGIN / 'design' / 'default-design.css').read_text(encoding='utf-8')
    return base + '\n/* %s */\n' % marker


@case
def test_design_set_and_default(env):
    p = env.baseline()
    f = TMP / ('design-%d.css' % (env.n))
    env.n += 1
    f.write_text(valid_design(env), encoding='utf-8')
    r = p.ok('design', 'set', f)
    assert 'design.css' in r.out
    assert p.man()['design'] == 'design.css'
    assert p.show('docs/artifacts/design.css') == f.read_text(encoding='utf-8')
    assert any(x.endswith('docs/artifacts/design.css') for x in dirty(p)), dirty(p)     # a file, not a commit
    assert dirty_outside(p) == []
    for name in ('feature-artifacts.html', 'feature-the-site.html', p.man()['full_progress_artifact']['file']):
        assert '#123456' in p.show('docs/artifacts/' + name), name
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
    f = TMP / ('bad-design-%d.css' % (env.n))
    env.n += 1
    f.write_text(':root { --nothing: 1; }\n', encoding='utf-8')
    before = p.head()
    r = p.run('design', 'set', f)
    assert r.code == 1 and has_line(r.err, 'R5.11') and 'token contract' in r.err, r.err
    assert p.head() == before and p.man()['design'] == 'default'
    r = p.run('design', 'set', TMP / 'no-such.css')
    assert r.code == 1 and 'does not exist' in r.err
    # a design.css that lost its tokens on main is a record finding
    g = TMP / ('ok-design-%d.css' % (env.n))
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
    f = TMP / ('regdesign-%d.css' % (env.n))
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


@case
def test_decisions_edit_content_renders_and_checks(env):
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
    assert 'data-glance-task="AR1"' in html and 'data-glance-decision="D2"' in html, html[html.index('class="lede"'):][:600]   # At a glance (R5.34)
    assert '1 decision open' in p.show('docs/artifacts/' + p.man()['full_progress_artifact']['file'])
    r = p.run('check')
    assert r.code == 0 and 'record is clean' in r.out and 'warning' not in r.out, r.all
    assert dirty_outside(p) == [], dirty(p)
    # an export carries decisions.json back out, and writing it back changes nothing
    d2 = export(p, 'artifacts', 'dec1b')
    assert (d2 / 'decisions.json').is_file()
    head = p.head()
    assert 'no change' in p.ok('edit-content', 'artifacts', '--from', d2).out and p.head() == head


@case
def test_decisions_invalid_file_writes_nothing(env):
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
    p = env.baseline()
    png = b'\x89PNG\r\n\x1a\n' + b'\r\n' * 5 + bytes(range(256))
    dec = [d_dec(1, options=[d_opt('A', image='assets/a.png'), d_opt('B')], chosen='B', owner_words=None)]
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, dec, 'img1', extra={'assets/a.png': png}))
    shown = (p.rdir / 'content' / 'artifacts' / 'assets' / 'a.png').read_bytes()
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
    p = env.baseline()
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1), d_open(2, task='AR1')], 'c1'))
    base = p.record_copy('decisions')
    assert check_record(env, base).code == 0

    def fresh(name):
        dest = TMP / ('dfx-%s' % (name))
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
    p = env.baseline()
    p.ok('edit-content', 'artifacts', '--from', edit_decisions(p, [d_dec(1)], 'wc1'))
    other = p.clone_again('other')
    path = other / 'docs' / 'artifacts' / 'content' / 'artifacts' / 'decisions.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['decisions'][0]['options'] = data['decisions'][0]['options'][:1]       # a single option: invalid
    path.write_text(json.dumps(data), encoding='utf-8')
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
    p.settle()


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
    files = p.files()
    # refusals change nothing
    for args, word in ((('mark-deleted', 'site', '--url', URL_A), 'belongs to'),
                       (('mark-deleted', '--url', 'https://claude.ai/artifact/never'), 'not in the retired list'),
                       (('mark-deleted', '--url', FP_URL), 'Full Progress'),
                       (('mark-deleted', 'site', '--url', 'nope'), 'http')):
        r = p.run(*args)
        assert r.code == 1 and word in r.err, (args, r.all)
        assert p.head() == before and p.files() == files
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
    p.settle()


@case
def test_stale_rule_copy_is_removed_with_the_migration_commit(env):
    """R10.6: a copy equal to a shipped rule text (any line endings) is deleted from the working tree, uncommitted, and says so."""
    p = env.baseline()
    push_file(p, 's1', STALE, RULE_1_0_0.replace('\n', '\r\n'))
    assert p.show(STALE) is not None
    local = p.clone / STALE
    head = p.head()
    r = p.ok('set-task-status', 'AR1', 'Waiting')
    assert 'removed .claude/rules/project-artifacts.md' in r.out, r.out
    assert p.show(STALE) is None and not local.exists()
    assert p.head() == head and ' D %s' % STALE in git(p.clone, 'status', '--porcelain').stdout, 'deleted, not committed'
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
# the plugin writes files and never git state (AR50, R4.13 - R4.17, R4.24, R4.28)
# --------------------------------------------------------------------------

NO_COMMIT = 'the plugin no longer commits or pushes (ARTIFACTSPEC 1.8.0); commit docs/artifacts/ when you choose'


@case
def test_writing_commands_change_files_and_leave_git_alone(env):
    """Every writing command changes files under docs/artifacts/ and leaves HEAD, the index, the refs, the stash
    and the remote exactly as they were; nothing is staged and nothing but the record (and .gitignore) changes."""
    p = env.baseline()
    d = export(p, 'artifacts', 'w1')
    (d / '02-more.html').write_text('<!-- title: More -->\n<p>More.</p>\n', encoding='utf-8')
    css = TMP / ('w-design-%d.css' % env.n)
    env.n += 1
    css.write_text(valid_design(env), encoding='utf-8')
    until = '2026-10-13T00:00:00+00:00'
    steps = [
        ('task-add', '--owner', 'artifacts', '--item', 'Hooks', '--detail', 'Three hooks.', '--expected', '14 Oct'),
        ('set-task-status', 'AR3', 'Waiting'),
        ('feature-new', '--key', 'extra', '--title', 'Extra', '--prefix', 'EX', '--apps', 'x'),
        ('edit-content', 'artifacts', '--from', d),
        ('design', 'set', css),
        ('render', '--all'),
        ('mark-published', 'full-progress', '--url', 'https://claude.ai/artifact/w'),
        ('mark-deferred', 'full-progress', '--until', until),
    ]
    state = p.git_state()
    for argv in steps:
        files = p.files()
        r = p.ok(*argv, env={'CLAUDE_ARTIFACTS_NOW': '2026-10-11T08:00:00+00:00'} if argv[0] == 'render' else None)
        assert p.files() != files, ('the record files changed', argv)
        assert p.git_state() == state, ('git state moved', argv, r.all)
        assert 'push' not in r.all.lower() or argv[0] == 'mark-published', r.all
        assert dirty_outside(p) == [], (argv, dirty_outside(p))
        assert git(p.clone, 'diff', '--cached', '--name-only').stdout.strip() == '', 'nothing is staged'
    changed = [x[3:] for x in dirty(p)]
    assert changed and all(x.startswith('docs/artifacts/') for x in changed), changed
    # the lock is a file outside docs/artifacts/, and it is gone when the command ends
    assert not [x for x in p.rdir.rglob('*') if 'lock' in x.name], 'no lock under docs/artifacts/'
    assert not (p.clone / '.claude' / 'artifacts-record.lock').exists()
    assert p.run('check').code == 0
    # --push and --no-push are accepted and do nothing (--push says so on stderr)
    r = p.ok('set-task-status', 'AR3', 'Running', '--push')
    assert NO_COMMIT in r.err and p.git_state() == state, r.all
    r = p.ok('set-task-status', 'AR3', 'Waiting', '--no-push')
    assert r.err == '' and p.git_state() == state, r.all


@case
def test_a_refused_change_leaves_every_file_as_it_was(env):
    p = env.baseline()
    files, state = p.files(), p.git_state()
    r = p.run('set-task-status', 'AR1', 'Waiting', '--expected', 'soon')
    assert r.code == 1 and 'nothing written' in r.err, r.all
    assert p.files() == files and p.git_state() == state and dirty(p) == []


@case
def test_commit_and_push_are_removed(env):
    """R4.28: both commands exit 1 with the one message; exit codes 3 and 4 are no longer used."""
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Waiting')
    state, files = p.git_state(), p.files()
    for argv in (('commit',), ('commit', '--retry'), ('commit', '--message', 'x', '--push'), ('push',), ('push', '--json')):
        r = p.run(*argv)
        assert r.code == 1 and NO_COMMIT in r.all, (argv, r.code, r.all)
        assert p.git_state() == state and p.files() == files, argv


@case
def test_pending_does_not_push(env):
    p = env.baseline()
    p.ok('set-task-status', 'AR1', 'Waiting')
    state = p.git_state()
    r = p.run('pending')
    assert r.code == 1 and r.out.startswith('publish full-progress (') and 'never published' in r.out, r.all
    assert 'push' not in r.all.lower()
    j = p.run('pending', '--json').json()
    assert sorted(j) == ['artifacts', 'queue', 'retired'] and 'push_error' not in j
    assert p.git_state() == state


@case
def test_worktree_prints_the_record_folder_and_ignores_the_old_setting(env):
    """R4.24: the record worktree is retired; the setting is ignored and check says so once, as a note."""
    p = env.baseline()
    where = TMP / ('elsewhere-%d' % env.n)
    env.n += 1
    assert same_path_str(p.ok('worktree').out.strip(), p.rdir)
    assert same_path_str(p.ok('worktree', env={'LUISMC_ARTIFACTS_WORKTREE': str(where)}).out.strip(), p.rdir)
    assert same_path_str(p.ok('worktree', env={'LUISMC_ARTIFACTS_WORKTREE': 'relative/path'}).out.strip(), p.rdir)
    assert same_path_str(p.ok('worktree', '--json').json()['worktree'], p.rdir)
    assert not where.exists()
    (p.clone / '.claude').mkdir(exist_ok=True)
    (p.clone / '.claude' / 'artifacts-local.json').write_text(json.dumps({'record_worktree': str(where)}), encoding='utf-8')
    r = p.run('set-task-status', 'AR1', 'Waiting')
    assert r.code == 0 and not where.exists() and p.task('AR1')['status'] == 'Waiting', r.all
    c = p.run('check', '--json')
    assert c.code == 0 and c.json()['findings'] == [], c.all
    assert len([n for n in c.json()['notes'] if 'ignored' in n and 'record_worktree' in n]) == 1, c.json()
    clean = env.baseline()
    assert not [n for n in clean.run('check', '--json').json()['notes'] if 'ignored' in n]


def same_path_str(a, b):
    return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))


def old_record(p, mutate=None):
    """An old record worktree at the default path holding a copy of the record (as 1.7.x left it)."""
    dest = p.old_wt / 'docs' / 'artifacts'
    shutil.copytree(str(p.rdir), str(dest))
    if mutate:
        mutate(dest)
    return p.old_wt


def newer_task(dest):
    edit_json(dest / 'registry.json', lambda r: task(r, 'AR1').update(
        status='Waiting', changed='2026-10-10T11:50:00+00:00'))
    edit_json(dest / 'registry.json', lambda r: r.update(updated='2026-10-10T11:50:00+00:00'))
    (dest / 'only-in-old.txt').write_text('old\n', encoding='utf-8')


@case
def test_migrate_copies_the_old_record_once_and_only_when_newer(env):
    """AR50 rule 4: copy when the old worktree's registry is newer, say so once, never remove it, change no git state."""
    p = env.baseline()
    state = p.git_state()
    # no old worktree: nothing, exit 0
    r = p.run('migrate')
    assert r.code == 0 and r.out == '' and r.err == '', r.all
    # an old copy that is not newer: nothing
    old = old_record(p)
    files = p.files()
    r = p.run('migrate')
    assert r.code == 0 and r.out == '' and p.files() == files, r.all
    # a newer one: copied, one line, the worktree stays
    newer_task(old / 'docs' / 'artifacts')
    r = p.run('migrate')
    assert r.code == 0 and len(r.out.strip().splitlines()) == 1, r.all
    assert r.out.startswith('luismc-artifacts: the record now lives in docs/artifacts/ and is never committed or pushed '
                            'by the plugin; copied it from '), r.out
    assert 'git worktree remove' in r.out and str(old).replace('\\', '/') .lower() in r.out.replace('\\', '/').lower()
    assert p.task('AR1')['status'] == 'Waiting' and (p.rdir / 'only-in-old.txt').is_file()
    assert old.is_dir() and (old / 'docs' / 'artifacts' / 'registry.json').is_file(), 'the plugin never removes it'
    assert p.git_state() == state
    # idempotent: the same copy is not newer any more
    r = p.run('migrate')
    assert r.code == 0 and r.out == '', r.all
    # the working tree moves on: an older old copy never overwrites it
    p.ok('set-task-status', 'AR1', 'Running', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-10T12:30:00+00:00'})
    r = p.run('migrate')
    assert r.code == 0 and r.out == '' and p.task('AR1')['status'] == 'Running', r.all


@case
def test_migrate_runs_before_a_writing_command(env):
    p = env.baseline()
    old_record(p, lambda dest: newer_task(dest))
    r = p.ok('task-add', '--owner', 'artifacts', '--item', 'Next', '--detail', 'd', '--expected', '14 Oct',
             env={'CLAUDE_ARTIFACTS_NOW': '2026-10-10T12:30:00+00:00'})
    assert 'copied it from' in r.err and p.task('AR1')['status'] == 'Waiting' and (p.rdir / 'only-in-old.txt').is_file(), r.all
    r = p.ok('set-task-status', 'AR1', 'Running', env={'CLAUDE_ARTIFACTS_NOW': '2026-10-10T12:40:00+00:00'})
    assert 'copied it from' not in r.all, r.all


@case
def test_migrate_brings_a_record_into_a_tree_that_has_none(env):
    p = env.project()
    q = env.baseline()
    old_dest = p.old_wt / 'docs' / 'artifacts'
    shutil.copytree(str(q.rdir), str(old_dest))
    p.run('pending')
    assert p.rdir.joinpath('manifest.json').is_file() and p.rdir.joinpath('registry.json').is_file()


@case
def test_only_read_only_git_is_run(env):
    """Rule 1: every git call the scripts make is one of the allowed read-only subcommands."""
    p = env.baseline()
    old_record(p, lambda dest: newer_task(dest))
    ip = InProc(env)
    allowed = {'rev-parse', 'symbolic-ref', 'status', 'diff', 'log', 'show', 'ls-files', 'config', 'worktree'}
    seen = []
    real = subprocess.run

    def spy(cmd, *a, **kw):
        if isinstance(cmd, (list, tuple)) and cmd and str(cmd[0]) == 'git':
            args, i = list(cmd[1:]), 0
            while i < len(args) and args[i] == '-c':
                i += 2
            seen.append(args[i:])
        return real(cmd, *a, **kw)

    d = export(p, 'artifacts', 'g1')
    subprocess.run = spy
    try:
        for argv in (('init', '--project', 'X'), ('migrate',), ('task-add', '--owner', 'artifacts', '--item', 'G', '--detail', 'd',
                                                                     '--expected', '14 Oct'),
                     ('set-task-status', 'AR1', 'Waiting'), ('edit-content', 'artifacts', '--from', str(d)),
                     ('render', '--all'), ('pending', '--json'), ('check',), ('path',), ('worktree',), ('queue', 'list'),
                     ('commit',), ('push',)):
            ip.call(p.clone, *argv)
    finally:
        subprocess.run = real
    assert seen, 'the scripts ask git for the repository root at least'
    bad = [a for a in seen if a[0] not in allowed or (a[0] == 'config' and '--get' not in a)
           or (a[0] == 'worktree' and a[1:2] != ['list'])]
    assert not bad, bad


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


def run_group():
    env = Env()
    passed = failed = skipped = 0
    for name, fn in TESTS:
        if ONLY and not any(o in name for o in ONLY):
            continue
        try:
            fn(env)
            passed += 1
            print('PASS  %s' % name)
        except Skipped as why:
            skipped += 1
            print('SKIP  %s: %s' % (name, why))
        except Exception:
            failed += 1
            print('FAIL  %s' % name)
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
        why = real_available()
        if why:
            print('SKIP  the suite is skipped: %s' % why)
        else:
            total_p, total_f, skipped = run_group()
            print('%d passed, %d failed, %d skipped' % (total_p, total_f, skipped))
    finally:
        _rmtree(TMP)
    return 1 if total_f else 0


if __name__ == '__main__':
    sys.exit(main())
