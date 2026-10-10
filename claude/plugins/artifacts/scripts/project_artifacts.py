#!/usr/bin/env python3
"""project_artifacts.py - the only writer of a project's artifact record.

Implements ARTIFACTSPEC 1.1.0: section 4 (the record, time, the record
worktree and its commits), section 7 (every command), the bookkeeping of
section 9 (`pending`, `mark-published`) and the record-level checks of
section 14. Rendering lives in render_artifacts.py, the queue in
artifact_queue.py. Python 3.10+, standard library only.

Exit codes: 0 success, 1 findings or a refused action, 2 unreadable record
(or a broken environment), 3 push race lost, 4 push refused by protection.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import difflib
import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import artifact_queue
except ImportError as _e:  # pragma: no cover - broken install
    artifact_queue = None
    _QUEUE_ERROR = str(_e)
try:
    import render_artifacts as R
except ImportError as _e:
    R = None
    _RENDER_ERROR = str(_e)

SPEC = 'ARTIFACTSPEC 1.0.0'
FP_NAME = 'full-progress'
RECORD_REL = 'docs/artifacts'
WORKTREE_REL = os.path.join('.claude', 'worktrees', 'artifacts-record')
PUSH_RETRIES = 3          # R4.15: retries after the first push attempt
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
KEY_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
PREFIX_RE = re.compile(r'^[A-Z]{2,5}$')
ID_RE = re.compile(r'^([A-Z]{2,5})([1-9][0-9]*)$')
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
EXPECTED_RE = re.compile(
    r'^(0[1-9]|[12][0-9]|3[01]) (?:' + '|'.join(MONTHS) + r')( ~([01][0-9]|2[0-3]):[0-5][0-9])?(; \S.*)?$')
TIME_EL_RE = re.compile(r'<time\b[^>]*\bdatetime="([^"]+)"')
RULE_NAME = 'project-artifacts.md'
GITIGNORE_LINES = ['.claude/artifacts-queue.json', '.claude/artifacts-stop-state.json', '.claude/worktrees/']

# Test seam (tests only): called as hook(ctx, attempt) right before each push.
_TEST_BEFORE_PUSH = None


# --------------------------------------------------------------------------
# failures and output
# --------------------------------------------------------------------------

class Fail(Exception):
    def __init__(self, code, msg, findings=None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.findings = findings or []


_WARNED = set()


def warn(msg):
    if msg in _WARNED:
        return
    _WARNED.add(msg)
    print('project_artifacts: warning: ' + msg, file=sys.stderr)


def fmt_finding(f):
    req, file, msg = f
    return '%s  %s: %s' % (req, file, msg)


def emit(args, result, human=None):
    """JSON when --json, else the human text (a string or list of lines)."""
    if getattr(args, 'json_out', False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif human is not None:
        print(human if isinstance(human, str) else '\n'.join(human))


# --------------------------------------------------------------------------
# time (R4.12)
# --------------------------------------------------------------------------

# Windows zone IDs for the zones people most often use; extend freely.
WINDOWS_ZONES = {
    'UTC': 'UTC', 'Etc/UTC': 'UTC',
    'Europe/Lisbon': 'GMT Standard Time', 'Europe/London': 'GMT Standard Time',
    'Europe/Dublin': 'GMT Standard Time', 'Atlantic/Azores': 'Azores Standard Time',
    'Europe/Madrid': 'Romance Standard Time', 'Europe/Paris': 'Romance Standard Time',
    'Europe/Brussels': 'Romance Standard Time', 'Europe/Copenhagen': 'Romance Standard Time',
    'Europe/Berlin': 'W. Europe Standard Time', 'Europe/Amsterdam': 'W. Europe Standard Time',
    'Europe/Rome': 'W. Europe Standard Time', 'Europe/Vienna': 'W. Europe Standard Time',
    'Europe/Stockholm': 'W. Europe Standard Time', 'Europe/Zurich': 'W. Europe Standard Time',
    'Europe/Warsaw': 'Central European Standard Time', 'Europe/Prague': 'Central Europe Standard Time',
    'Europe/Athens': 'GTB Standard Time', 'Europe/Helsinki': 'FLE Standard Time',
    'Europe/Istanbul': 'Turkey Standard Time', 'Europe/Moscow': 'Russian Standard Time',
    'America/New_York': 'Eastern Standard Time', 'America/Toronto': 'Eastern Standard Time',
    'America/Chicago': 'Central Standard Time', 'America/Denver': 'Mountain Standard Time',
    'America/Phoenix': 'US Mountain Standard Time', 'America/Los_Angeles': 'Pacific Standard Time',
    'America/Vancouver': 'Pacific Standard Time', 'America/Mexico_City': 'Central Standard Time (Mexico)',
    'America/Sao_Paulo': 'E. South America Standard Time',
    'America/Argentina/Buenos_Aires': 'Argentina Standard Time',
    'Africa/Johannesburg': 'South Africa Standard Time', 'Africa/Cairo': 'Egypt Standard Time',
    'Asia/Dubai': 'Arabian Standard Time', 'Asia/Kolkata': 'India Standard Time',
    'Asia/Shanghai': 'China Standard Time', 'Asia/Singapore': 'Singapore Standard Time',
    'Asia/Tokyo': 'Tokyo Standard Time', 'Asia/Seoul': 'Korea Standard Time',
    'Australia/Sydney': 'AUS Eastern Standard Time', 'Australia/Perth': 'W. Australia Standard Time',
    'Pacific/Auckland': 'New Zealand Standard Time',
}


def windows_to_iana(win):
    for iana, w in WINDOWS_ZONES.items():
        if w == win:
            return iana
    return None


def local_zone_guess():
    """(iana, windows_id) of the machine, either may be None."""
    tz = os.environ.get('TZ', '')
    if '/' in tz:
        return tz.lstrip(':'), WINDOWS_ZONES.get(tz.lstrip(':'))
    for p in ('/etc/timezone',):
        try:
            v = Path(p).read_text(encoding='utf-8').strip()
            if v:
                return v, WINDOWS_ZONES.get(v)
        except OSError:
            pass
    try:
        target = os.path.realpath('/etc/localtime').replace('\\', '/')
        if '/zoneinfo/' in target:
            v = target.split('/zoneinfo/', 1)[1]
            return v, WINDOWS_ZONES.get(v)
    except OSError:
        pass
    if os.name == 'nt':
        try:
            out = subprocess.run(['tzutil', '/g'], capture_output=True, text=True, timeout=10)
            win = out.stdout.strip()
            if out.returncode == 0 and win:
                return windows_to_iana(win), win
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None, None


def current_instant():
    """The real clock; CLAUDE_ARTIFACTS_NOW (ISO, tests only) overrides it."""
    forced = os.environ.get('CLAUDE_ARTIFACTS_NOW')
    if forced:
        dt = datetime.fromisoformat(forced.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _zoneinfo_now(instant, zone):
    if os.environ.get('CLAUDE_ARTIFACTS_NO_ZONEINFO'):
        return None
    try:
        from zoneinfo import ZoneInfo
        return instant.astimezone(ZoneInfo(zone))
    except Exception:  # missing tzdata, bad name, no zoneinfo module
        return None


def _powershell_now(instant, win_zone):
    if not win_zone or "'" in win_zone or os.environ.get('CLAUDE_ARTIFACTS_NO_POWERSHELL'):
        return None
    exe = shutil.which('powershell') or shutil.which('pwsh')
    if not exe:
        return None
    if os.environ.get('CLAUDE_ARTIFACTS_NOW'):
        u = ("[DateTime]::SpecifyKind([DateTime]::ParseExact('%s','yyyy-MM-ddTHH:mm:ss',"
             "[Globalization.CultureInfo]::InvariantCulture),[DateTimeKind]::Utc)"
             % instant.strftime('%Y-%m-%dT%H:%M:%S'))
    else:
        u = '[DateTime]::UtcNow'
    script = ("$u=%s;$z=[System.TimeZoneInfo]::FindSystemTimeZoneById('%s');"
              "$t=[System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId($u,'%s');"
              "$o=$z.GetUtcOffset($u);"
              "'{0}|{1}' -f $t.ToString('yyyy-MM-ddTHH:mm:ss',[Globalization.CultureInfo]::InvariantCulture),[int]$o.TotalMinutes"
              % (u, win_zone, win_zone))
    try:
        out = subprocess.run([exe, '-NoProfile', '-NonInteractive', '-Command', script],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\|(-?\d+)', out.stdout or '')
    if out.returncode != 0 or not m:
        return None
    naive = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')
    return naive.replace(tzinfo=timezone(timedelta(minutes=int(m.group(2)))))


class TimeInfo:
    def __init__(self, dt):
        self.dt = dt
        self.text = stamp_text(dt)          # DD Mon HH:MM
        self.iso = dt.isoformat(timespec='minutes')
        self.date = '%02d %s' % (dt.day, MONTHS[dt.month - 1])


def stamp_text(dt):
    return '%02d %s %02d:%02d' % (dt.day, MONTHS[dt.month - 1], dt.hour, dt.minute)


def stamp_text_from_iso(iso):
    return stamp_text(datetime.fromisoformat(iso.replace('Z', '+00:00')))


def now_in_zone(zone, win_zone):
    instant = current_instant()
    dt = _zoneinfo_now(instant, zone) if zone else None
    if dt is None:
        dt = _powershell_now(instant, win_zone)
    if dt is None:
        warn('time zone data for %s is not available and PowerShell could not convert it; '
             'using the machine\'s local time' % (zone or 'the project zone'))
        dt = instant.astimezone()
    return TimeInfo(dt)


def parse_iso(s):
    try:
        dt = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else None


# --------------------------------------------------------------------------
# git and the record worktree (R4.13 - R4.17)
# --------------------------------------------------------------------------

def git(cwd, *a, check=False, ok=(0,)):
    cmd = ['git', '-c', 'core.autocrlf=false', '-c', 'core.safecrlf=false',
           '-c', 'core.quotepath=off', '-c', 'core.longpaths=true'] + list(a)
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env=env)
    except OSError as e:
        raise Fail(2, 'git is not available: %s' % e)
    if check and r.returncode not in ok:
        raise Fail(2, 'git %s failed: %s' % (' '.join(a[:2]), (r.stderr or r.stdout).strip()))
    return r


def git_out(cwd, *a):
    r = git(cwd, *a)
    return r.stdout.strip() if r.returncode == 0 else None


def session_root(start=None):
    top = artifact_queue.repo_root(start)
    if not top:
        return None
    norm = top.replace('\\', '/')
    tail = '/.claude/worktrees/artifacts-record'
    if norm.endswith(tail):
        return norm[:-len(tail)]
    return top


class Ctx:
    def __init__(self, root, branch):
        self.root = Path(root)
        self.branch = branch
        self.wt = self.root / WORKTREE_REL
        self.record_dir = self.wt / RECORD_REL
        self.attempt = 0


def detect_default_branch(root, given=None):
    if given:
        return given
    ref = git_out(root, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD')
    if ref and ref.startswith('origin/'):
        return ref[len('origin/'):]
    r = git(root, 'ls-remote', '--symref', 'origin', 'HEAD')
    m = re.search(r'ref: refs/heads/(\S+)\s+HEAD', r.stdout or '')
    if m:
        return m.group(1)
    for b in ('main', 'master'):
        if git(root, 'rev-parse', '--verify', '-q', 'refs/remotes/origin/' + b).returncode == 0:
            return b
    raise Fail(2, 'cannot tell the default branch (no origin/HEAD); pass --default-branch')


def make_ctx(args, branch=None):
    if artifact_queue is None:
        raise Fail(2, 'artifact_queue.py cannot be imported: %s' % _QUEUE_ERROR)
    root = session_root()
    if not root:
        raise Fail(2, 'not inside a git repository')
    ctx = Ctx(root, branch or detect_default_branch(root, getattr(args, 'default_branch', None)))
    ctx.no_push = bool(getattr(args, 'no_push', False))
    return ctx


@contextlib.contextmanager
def locked(ctx):
    ctx.wt.parent.mkdir(parents=True, exist_ok=True)
    p = ctx.wt.parent / 'artifacts-record.lock'
    deadline = time.time() + 60
    while True:
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - p.stat().st_mtime > 300:
                    p.unlink()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise Fail(1, 'the record worktree is locked by another invocation (%s)' % p)
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            p.unlink()
        except OSError:
            pass


def fetch(ctx, tolerant=False):
    b = ctx.branch
    r = git(ctx.root, 'fetch', '--quiet', 'origin', '+refs/heads/%s:refs/remotes/origin/%s' % (b, b))
    if r.returncode != 0:
        if tolerant:
            warn('git fetch origin failed (%s); using the last fetched state' % (r.stderr or '').strip()[:120])
            return False
        raise Fail(2, 'git fetch origin %s failed: %s' % (b, (r.stderr or r.stdout).strip()))
    return True


def no_record_fail(ctx):
    return Fail(2, 'no record in this repository (origin/%s has no %s/manifest.json); run init' % (ctx.branch, RECORD_REL))


def ensure_sparse(ctx):
    """Check out docs/artifacts/ only (a long path elsewhere must not break the worktree)."""
    r = git(ctx.wt, 'config', '--get', 'core.sparseCheckout')
    if r.stdout.strip() != 'true':
        git(ctx.wt, 'sparse-checkout', 'set', '--no-cone', '/%s/' % RECORD_REL, check=True)


def ensure_worktree(ctx, tolerant=False, create=False):
    """Fetch and create the detached, sparse record worktree on first use.

    Only init and feature-new (create=True) may create it; any other command
    exits 2 when origin/<default> has no record, leaving no worktree behind.
    """
    fetched = fetch(ctx, tolerant)
    wt = ctx.wt
    if (wt / '.git').exists():
        ensure_sparse(ctx)
        return fetched
    if git(ctx.root, 'rev-parse', '--verify', '-q', 'refs/remotes/origin/' + ctx.branch).returncode != 0:
        raise Fail(2, 'origin/%s does not exist' % ctx.branch)
    if not create and git(ctx.root, 'cat-file', '-e',
                          'refs/remotes/origin/%s:%s/manifest.json' % (ctx.branch, RECORD_REL)).returncode != 0:
        raise no_record_fail(ctx)
    git(ctx.root, 'worktree', 'prune')
    if wt.exists() and any(wt.iterdir()):
        raise Fail(2, '%s exists but is not a git worktree; remove it' % wt)
    wt.parent.mkdir(parents=True, exist_ok=True)
    git(ctx.root, 'worktree', 'add', '--detach', '--no-checkout', '--quiet', str(wt), 'origin/' + ctx.branch, check=True)
    ensure_sparse(ctx)
    git(ctx.wt, 'reset', '--hard', '--quiet', 'origin/' + ctx.branch, check=True)
    return fetched


def dirty_paths(ctx):
    r = git(ctx.wt, 'status', '--porcelain', '-z', '--untracked-files=all', '--', RECORD_REL)
    return sorted(p[3:] for p in r.stdout.split('\0') if len(p) > 3)


def ahead_count(ctx):
    r = git(ctx.wt, 'rev-list', '--count', 'origin/%s..HEAD' % ctx.branch)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def head_sha(ctx):
    return git_out(ctx.wt, 'rev-parse', 'HEAD')


def clean_worktree(ctx, to=None):
    git(ctx.wt, 'reset', '--hard', '--quiet', to or 'HEAD')
    git(ctx.wt, 'clean', '-fdq', '--', RECORD_REL)


def sync(ctx, readonly=False, create=False):
    """Fetch and reset the record worktree to origin/<default_branch> (R4.13).

    Unpushed record commits (kept after a refused push or --no-push) are
    rebased onto it, not dropped. Uncommitted edits are discarded: the session
    never edits this worktree (it uses export-content / edit-content).
    """
    ensure_worktree(ctx, tolerant=readonly, create=create)
    if dirty_paths(ctx):
        clean_worktree(ctx)
    if git(ctx.wt, 'rev-parse', '--verify', '-q', 'origin/' + ctx.branch).returncode != 0:
        raise Fail(2, 'origin/%s does not exist' % ctx.branch)
    if ahead_count(ctx):
        r = git(ctx.wt, 'rebase', '--quiet', 'origin/' + ctx.branch)
        if r.returncode != 0:
            git(ctx.wt, 'rebase', '--abort')
            raise Fail(2, 'cannot rebase the unpushed record commit onto origin/%s: %s'
                       % (ctx.branch, (r.stderr or r.stdout).strip()[:200]))
    else:
        git(ctx.wt, 'reset', '--hard', '--quiet', 'origin/' + ctx.branch, check=True)
    git(ctx.wt, 'clean', '-fdq', '--', RECORD_REL)


def commit_record(ctx, message):
    """R4.14: commit only docs/artifacts/**; returns the new SHA or None."""
    git(ctx.wt, 'add', '-A', '--', RECORD_REL, check=True)
    names = [n for n in git(ctx.wt, 'diff', '--cached', '--name-only', '-z').stdout.split('\0') if n]
    bad = [n for n in names if not n.startswith(RECORD_REL + '/')]
    if bad:
        git(ctx.wt, 'reset', '--quiet')
        raise Fail(1, 'refusing to commit paths outside %s/: %s' % (RECORD_REL, bad[0]))
    if not names:
        return None
    ident = []
    if not git_out(ctx.wt, 'config', 'user.name'):
        ident += ['-c', 'user.name=project-artifacts']
    if not git_out(ctx.wt, 'config', 'user.email'):
        ident += ['-c', 'user.email=project-artifacts@localhost']
    r = git(ctx.wt, *(ident + ['commit', '--quiet', '-m', message]))
    if r.returncode != 0:
        raise Fail(2, 'git commit failed: %s' % (r.stderr or r.stdout).strip()[:300])
    return head_sha(ctx)


def push(ctx):
    """One push attempt: 'ok', 'race', 'refused' or ('error', text)."""
    if _TEST_BEFORE_PUSH is not None:
        _TEST_BEFORE_PUSH(ctx, ctx.attempt)
    r = git(ctx.wt, 'push', '--quiet', 'origin', 'HEAD:refs/heads/%s' % ctx.branch)
    if r.returncode == 0:
        return 'ok'
    t = ((r.stderr or '') + (r.stdout or '')).lower()
    if 'non-fast-forward' in t or 'fetch first' in t or 'stale info' in t or \
            ('[rejected]' in t and '[remote rejected]' not in t):
        return 'race'
    if any(s in t for s in ('remote rejected', 'protected branch', 'gh006', 'gh013',
                            'hook declined', 'permission denied', 'denied')):
        return 'refused'
    return ('error', (r.stderr or r.stdout).strip()[:300])


def refused_fail(ctx):
    return Fail(4, 'record push refused by %s protection' % ctx.branch)


def race_fail():
    return Fail(3, 'record push lost the race %d times; nothing was committed' % (PUSH_RETRIES + 1))


# --------------------------------------------------------------------------
# the record
# --------------------------------------------------------------------------

def read_json(p):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise Fail(2, 'unreadable record file %s: %s' % (p.name, e))


def dump_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + '\n'


def write_text(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.replace('\r\n', '\n').encode('utf-8'))


def sha_of_file(p):
    return hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def read_html(p):
    try:
        return p.read_bytes().replace(b'\r\n', b'\n').decode('utf-8')
    except OSError:
        return None


def existing_stamp(html):
    """ISO stamp of a rendered file (its <time datetime>), or None."""
    if not html:
        return None
    m = TIME_EL_RE.search(html)
    if not m or parse_iso(m.group(1)) is None:
        return None
    return m.group(1)


def task_sort_key(t):
    m = ID_RE.match(str(t.get('id', '')))
    return (m.group(1), int(m.group(2))) if m else (str(t.get('id', '')), 0)


class Record:
    def __init__(self, d, manifest=None, registry=None, exists=True):
        self.dir = Path(d)
        self.manifest = manifest
        self.registry = registry
        self._tasks0 = (copy.deepcopy(self.tasks()) if isinstance(registry, dict) else None)
        self.exists = exists
        self._now = None
        self._contents = None
        self.render_keys = {}        # key -> 'new': render with a new stamp
        self.rendered = set()
        self.message = None

    @classmethod
    def load(cls, d):
        d = Path(d)
        mp, rp = d / 'manifest.json', d / 'registry.json'
        if not mp.is_file():
            raise Fail(2, 'no artifact record: %s is missing (run init)' % mp)
        manifest = read_json(mp)
        if not rp.is_file():
            raise Fail(2, 'unreadable record: %s is missing' % rp)
        registry = read_json(rp)
        if not isinstance(manifest, dict) or not isinstance(registry, dict):
            raise Fail(2, 'unreadable record: manifest.json and registry.json must be objects')
        return cls(d, manifest, registry)

    def artifacts(self):
        """[(key, kind, entry)], full-progress first. Tolerates a damaged manifest."""
        out = []
        fp = self.manifest.get('full_progress_artifact')
        if isinstance(fp, dict) and fp:
            out.append((fp.get('key', FP_NAME), 'full-progress', fp))
        feats = self.manifest.get('feature_artifacts')
        for e in feats if isinstance(feats, list) else []:
            if isinstance(e, dict):
                out.append((e.get('key'), 'feature', e))
        return out

    def entry(self, key):
        for k, _kind, e in self.artifacts():
            if k == key:
                return e
        return None

    def kind(self, key):
        for k, kind, _e in self.artifacts():
            if k == key:
                return kind
        return None

    def tasks(self):
        t = self.registry.get('tasks')
        return t if isinstance(t, list) else []

    def now(self):
        if self._now is None:
            m = self.manifest
            self._now = now_in_zone(m.get('timezone'), m.get('windows_timezone'))
        return self._now

    def registry_changed(self):
        """True when the task list differs from what was loaded (or the registry is new)."""
        reg = self.registry
        return (self._tasks0 is None or not isinstance(reg, dict) or not reg.get('updated')
                or self.tasks() != self._tasks0)

    def touch(self):
        """Stamp `updated`: the manifest always; the registry only when a task changed.

        The full-progress artifact embeds the whole registry (R5.9), so its `updated`
        must not move on commands that change no task (mark-published, design, ...).
        """
        iso = self.now().iso
        self.manifest['updated'] = iso
        if self.registry_changed():
            self.registry['updated'] = iso

    def sort_tasks(self):
        self.registry['tasks'] = sorted(self.tasks(), key=task_sort_key)

    def contents(self):
        if self._contents is None:
            c, findings = load_contents(self)
            if findings:
                raise Fail(1, 'content is invalid; nothing written', findings)
            self._contents = c
        return self._contents

    def invalidate(self):
        self._contents = None

    def html_path(self, key):
        return self.dir / self.entry(key)['file']

    def write_html(self, key, html):
        write_text(self.html_path(key), html)
        self.rendered.add(key)


REQ_RE = re.compile(r'\b(R\d+\.\d+[a-z]?|INV-\d)\b')


def problems_to_findings(problems, key):
    out = []
    for p in problems or []:
        if isinstance(p, (tuple, list)) and len(p) >= 2:
            out.append((str(p[0]), 'content/%s' % key, str(p[1])))
        else:
            m = REQ_RE.search(str(p))
            out.append((m.group(1) if m else 'R4.1', 'content/%s' % key, str(p)))
    return out


def _load_content(record_dir, key):
    try:
        takes_plugin = 'plugin_dir' in inspect.signature(R.load_content).parameters
    except (TypeError, ValueError):
        takes_plugin = False
    if takes_plugin:
        return R.load_content(record_dir, key, plugin_dir=str(PLUGIN_DIR))
    return R.load_content(record_dir, key)


def load_contents(rec):
    contents, findings = {}, []
    for key, _kind, _e in rec.artifacts():
        if not isinstance(key, str) or not KEY_RE.match(key):
            continue
        try:
            contents[key] = _load_content(rec.dir, key)
        except R.ContentError as ce:
            findings += problems_to_findings(getattr(ce, 'problems', None) or [str(ce)], key)
        except Exception as e:  # unreadable content of any kind
            findings.append(('R4.1', 'content/%s' % key, 'content cannot be read: %s' % e))
    return contents, findings


def render_one(rec, key, stamp_t, stamp_i):
    try:
        return R.render_artifact(rec.manifest, rec.registry, rec.contents(), key, PLUGIN_DIR,
                                 rec.dir, stamp_t, stamp_i)
    except Fail:
        raise
    except R.ContentError as ce:
        raise Fail(1, 'content is invalid; nothing written',
                   problems_to_findings(getattr(ce, 'problems', None) or [str(ce)], key))
    except Exception as e:
        raise Fail(2, 'render of %s failed: %s: %s' % (key, type(e).__name__, e))


def rerender_existing(rec):
    """Re-render every artifact that has a file, keeping its stamp; returns keys written."""
    written = []
    for key, _kind, e in rec.artifacts():
        old = read_html(rec.dir / e['file'])
        st = existing_stamp(old)
        if st is None:
            continue
        html = render_one(rec, key, stamp_text_from_iso(st), st)
        if html.replace('\r\n', '\n') != old:
            rec.write_html(key, html)
            written.append(key)
    return written


# --------------------------------------------------------------------------
# validation (R7.1; the record-level checks of section 14)
# --------------------------------------------------------------------------

def validate_structure(rec):
    """Record-level checks. Returns sorted unique findings (req, file, message)."""
    F = []

    def f(req, file, msg):
        F.append((req, file, msg))

    m, reg = rec.manifest, rec.registry
    statuses = list(R.STATUSES) if R is not None else []

    # -- manifest fields
    for k in ('spec', 'project', 'timezone', 'timezone_label', 'default_branch', 'merged_status',
              'design', 'updated'):
        if not isinstance(m.get(k), str) or not m.get(k):
            f('R4.2', 'manifest.json', 'field "%s" is missing or not a non-empty string' % k)
    if not isinstance(m.get('windows_timezone'), str):
        f('R4.2', 'manifest.json', 'field "windows_timezone" is missing or not a string')
    if m.get('spec') != SPEC:
        f('R4.2', 'manifest.json', 'spec must be "%s"' % SPEC)
    if m.get('merged_status') not in ('Live', 'Done'):
        f('R4.2', 'manifest.json', 'merged_status must be "Live" or "Done"')
    if m.get('design') not in ('default', 'design.css'):
        f('R4.2', 'manifest.json', 'design must be "default" or "design.css"')
    elif m.get('design') == 'design.css' and not (rec.dir / 'design.css').is_file():
        f('R5.10', 'manifest.json', 'design is "design.css" but docs/artifacts/design.css is missing')
    elif m.get('design') == 'design.css' and getattr(R, 'check_tokens', None):
        try:
            for prob in R.check_tokens(read_html(rec.dir / 'design.css') or ''):
                f('R5.11', 'design.css', prob)
        except Exception as ex:
            f('R5.11', 'design.css', 'cannot be checked: %s' % ex)
    if isinstance(m.get('updated'), str) and m['updated'] and parse_iso(m['updated']) is None:
        f('R4.2', 'manifest.json', 'updated is not an ISO time with offset')

    pp = m.get('project_prefixes')
    if not isinstance(pp, list) or not all(isinstance(x, str) and PREFIX_RE.match(x) for x in pp):
        f('R4.2', 'manifest.json', 'project_prefixes must be a list of 2 to 5 capital letters')
        pp = []

    # -- artifacts
    fp = m.get('full_progress_artifact')
    feats = m.get('feature_artifacts')
    if not isinstance(feats, list):
        f('R4.2', 'manifest.json', 'feature_artifacts must be a list')
        feats = []
    feats = [e for e in feats if isinstance(e, dict)]

    fp_ok = isinstance(fp, dict) and bool(fp)
    if not fp_ok:
        if feats:
            f('INV-2', 'manifest.json', 'a feature artifact exists but there is no full-progress artifact')
    else:
        if fp.get('key') != FP_NAME:
            f('R4.2', 'manifest.json', 'the full-progress artifact key must be "%s"' % FP_NAME)
    for e in feats:
        if e.get('key') == FP_NAME or str(e.get('title', '')).startswith('Full Progress: '):
            f('INV-2', 'manifest.json', 'a second full-progress artifact is listed (%s)' % e.get('key'))
    if fp_ok and rec.dir.is_dir():
        for p in sorted(rec.dir.glob('full-progress-*.html')):
            if p.name != fp.get('file'):
                f('INV-2', p.name, 'a second full-progress artifact file exists')

    def check_entry(e, kind):
        key = e.get('key')
        label = key if isinstance(key, str) else '?'
        if not isinstance(key, str) or not KEY_RE.match(key):
            f('R4.2', 'manifest.json', 'artifact key %r is not lowercase letters, digits and hyphens' % key)
        for fld in ('title', 'file', 'url', 'published_sha256'):
            if not isinstance(e.get(fld), str):
                f('R4.3' if fld in ('url', 'published_sha256') else 'R4.2', 'manifest.json',
                  '%s: field "%s" is missing or not a string' % (label, fld))
        url, h = e.get('url'), e.get('published_sha256')
        if isinstance(url, str) and url and not re.match(r'^https?://\S+$', url):
            f('R4.3', 'manifest.json', '%s: url is not an http(s) URL' % label)
        if isinstance(h, str) and h and not SHA_RE.match(h):
            f('R4.3', 'manifest.json', '%s: published_sha256 is not a SHA-256' % label)
        if h and not url:
            f('R4.3', 'manifest.json', '%s: published_sha256 is set but url is empty' % label)
        title = e.get('title')
        want = 'Full Progress: ' if kind == 'full-progress' else 'Feature: '
        if isinstance(title, str):
            if not title.startswith(want):
                f('R5.1', 'manifest.json', '%s: title must start with "%s"' % (label, want))
            else:
                try:
                    exp = R.artifact_file(kind, title)
                    if e.get('file') != exp:
                        f('R4.4', 'manifest.json', '%s: file must be %s' % (label, exp))
                except Exception as ex:
                    f('R4.4', 'manifest.json', '%s: file name cannot be derived: %s' % (label, ex))
        if kind == 'feature':
            if not isinstance(e.get('prefix'), str) or not PREFIX_RE.match(e.get('prefix', '')):
                f('R4.2', 'manifest.json', '%s: prefix must be 2 to 5 capital letters' % label)
            if not isinstance(e.get('apps'), list) or not all(isinstance(a, str) for a in e.get('apps', [])):
                f('R4.2', 'manifest.json', '%s: apps must be a list of strings' % label)

    if fp_ok:
        check_entry(fp, 'full-progress')
    for e in feats:
        check_entry(e, 'feature')

    keys = [e.get('key') for e in feats] + ([fp.get('key')] if fp_ok else [])
    for k in sorted({x for x in keys if keys.count(x) > 1 and isinstance(x, str)}):
        f('R4.2', 'manifest.json', 'artifact key "%s" appears more than once' % k)
    prefixes = [e.get('prefix') for e in feats] + list(pp)
    for p in sorted({x for x in prefixes if prefixes.count(x) > 1 and isinstance(x, str)}):
        f('R4.2', 'manifest.json', 'prefix "%s" appears more than once across the manifest' % p)

    # -- registry
    if reg.get('spec') != SPEC:
        f('R4.2', 'registry.json', 'spec must be "%s"' % SPEC)
    if not isinstance(reg.get('updated'), str) or parse_iso(reg.get('updated')) is None:
        f('R4.2', 'registry.json', 'updated is not an ISO time with offset')
    tasks = reg.get('tasks')
    if not isinstance(tasks, list):
        f('R4.3', 'registry.json', 'tasks must be a list')
        tasks = []
    feat_by_name = {e.get('key'): e for e in feats}
    seen = {}
    for t in tasks:
        if not isinstance(t, dict):
            f('R4.5', 'registry.json', 'a task is not an object')
            continue
        tid = t.get('id')
        label = tid if isinstance(tid, str) else '?'
        for fld in ('id', 'owner', 'app', 'status', 'item', 'detail', 'expected', 'changed'):
            if not isinstance(t.get(fld), str):
                f('R4.5', 'registry.json', '%s: field "%s" is missing or not a string' % (label, fld))
        mt = ID_RE.match(tid) if isinstance(tid, str) else None
        if not mt:
            f('R4.5', 'registry.json', '%s: id is not a registered prefix plus a positive integer' % label)
        elif tid in seen:
            f('R4.5', 'registry.json', '%s: id appears more than once' % tid)
        seen[tid] = seen.get(tid, 0) + 1
        owner = t.get('owner')
        if owner == 'project':
            if mt and mt.group(1) not in pp:
                f('R4.6', 'registry.json', '%s: prefix %s is not a project prefix' % (label, mt.group(1)))
        elif owner in feat_by_name:
            if mt and mt.group(1) != feat_by_name[owner].get('prefix') and mt.group(1) not in pp:
                f('R4.6', 'registry.json', '%s: prefix %s is neither the prefix of "%s" (%s) nor a project prefix'
                  % (label, mt.group(1), owner, feat_by_name[owner].get('prefix')))
        elif isinstance(owner, str):
            f('R4.6', 'registry.json', '%s: owner "%s" is neither project nor a feature key' % (label, owner))
        st = t.get('status')
        if isinstance(st, str) and st not in statuses:
            f('R4.7', 'registry.json', '%s: status "%s" is not one of the eight statuses' % (label, st))
        if isinstance(t.get('changed'), str) and parse_iso(t['changed']) is None:
            f('R4.7', 'registry.json', '%s: changed is not an ISO time with offset' % label)
        if isinstance(t.get('item'), str) and len(t['item']) > 80:
            f('R4.8', 'registry.json', '%s: item is longer than 80 characters' % label)
        if isinstance(t.get('detail'), str) and len(t['detail']) > 600:
            f('R4.8', 'registry.json', '%s: detail is longer than 600 characters' % label)
        ex = t.get('expected')
        if isinstance(ex, str) and isinstance(st, str) and st in statuses:
            if st in ('Live', 'Done'):
                if not EXPECTED_RE.match(ex):
                    f('R6.7', 'registry.json', '%s: Expected on a %s row must be the date it happened (DD Mon), got "%s"'
                      % (label, st, ex))
            elif st == 'Failed':
                if ex and not EXPECTED_RE.match(ex):
                    f('R6.6', 'registry.json', '%s: Expected must be empty or "DD Mon [~HH:MM][; note]", got "%s"'
                      % (label, ex))
            elif not EXPECTED_RE.match(ex):
                f('R6.6', 'registry.json', '%s: Expected must be "DD Mon [~HH:MM][; note]", got "%s"' % (label, ex))
    ids = [t.get('id') for t in tasks if isinstance(t, dict)]
    if [i for i in ids if isinstance(i, str)] != [t.get('id') for t in sorted(
            [t for t in tasks if isinstance(t, dict) and isinstance(t.get('id'), str)], key=task_sort_key)]:
        f('R4.9', 'registry.json', 'tasks are not stored in ID order (prefix, then number)')

    # -- content
    _c, cf = load_contents(rec)
    F.extend(cf)
    known = {k for k in keys if isinstance(k, str)}
    cdir = rec.dir / 'content'
    if cdir.is_dir():
        for p in sorted(cdir.iterdir()):
            if p.is_dir() and p.name not in known:
                f('R4.1', 'content/%s' % p.name, 'content folder has no artifact in the manifest')
    return sorted(set(F))


def check_html_findings(rec, key):
    e = rec.entry(key)
    html = read_html(rec.dir / e['file'])
    if html is None:
        return [('INV-3', e['file'], 'rendered file is missing; run render')]
    out = []
    try:
        res = R.check_html(html, key, rec.manifest, rec.registry, PLUGIN_DIR, rec.dir)
    except Exception as ex:
        raise Fail(2, 'check_html of %s failed: %s: %s' % (key, type(ex).__name__, ex))
    for item in res or []:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            out.append((str(item[0]), e['file'], str(item[1])))
        else:
            out.append(('R5.3', e['file'], str(item)))
    return out


def fresh_render_findings(rec, key):
    """INV-3: the file equals what rendering the record produces now."""
    e = rec.entry(key)
    old = read_html(rec.dir / e['file'])
    if old is None:
        return []          # reported by check_html_findings
    st = existing_stamp(old)
    if st is None:
        return [('INV-3', e['file'], 'the rendered file has no <time datetime> stamp, so it cannot be compared')]
    try:
        fresh = render_one(rec, key, stamp_text_from_iso(st), st)
    except Fail as fl:
        return fl.findings or [('INV-3', e['file'], fl.msg)]
    if fresh.replace('\r\n', '\n') != old:
        return [('INV-3', e['file'], 'rendered HTML differs from a fresh render of the record; run render')]
    return []


# --------------------------------------------------------------------------
# statuses (R7.3)
# --------------------------------------------------------------------------

SYNONYMS = {
    'merged': 'Live', 'released': 'Live', 'shipped': 'Live', 'deployed': 'Live', 'production': 'Live',
    'prod': 'Live', 'published': 'Live', 'launched': 'Live', 'released to production': 'Live',
    'complete': 'Done', 'completed': 'Done', 'finished': 'Done', 'closed': 'Done', 'resolved': 'Done',
    'in progress': 'Running', 'started': 'Running', 'active': 'Running', 'working': 'Running',
    'wip': 'Running', 'ongoing': 'Running', 'open': 'Running', 'run': 'Running',
    'blocked': 'Needs you', 'review': 'Needs you', 'needs review': 'Needs you',
    'needs input': 'Needs you', 'awaiting you': 'Needs you', 'need you': 'Needs you', 'needs': 'Needs you',
    'pending': 'Waiting', 'ci': 'Waiting', 'queued': 'Waiting', 'wait': 'Waiting',
    'planned': 'To do', 'todo': 'To do', 'not started': 'To do', 'backlog': 'To do', 'new': 'To do',
    'draft': 'To do',
    'paused': 'On hold', 'hold': 'On hold', 'deferred': 'On hold', 'postponed': 'On hold',
    'parked': 'On hold', 'onhold': 'On hold',
    'failing': 'Failed', 'failure': 'Failed', 'broken': 'Failed', 'error': 'Failed',
    'errored': 'Failed', 'red': 'Failed', 'rejected': 'Failed', 'fail': 'Failed',
}


def nearest_status(word):
    allowed = list(R.STATUSES)
    norm = re.sub(r'[\s_-]+', ' ', str(word).strip().lower())
    for s in allowed:
        if re.sub(r'[\s_-]+', ' ', s.lower()) == norm:
            return s
    if norm in SYNONYMS and SYNONYMS[norm] in allowed:
        return SYNONYMS[norm]
    pool = {re.sub(r'[\s_-]+', ' ', s.lower()): s for s in allowed}
    pool.update({k: v for k, v in SYNONYMS.items() if v in allowed})
    close = difflib.get_close_matches(norm, list(pool), n=1, cutoff=0.6)
    return pool[close[0]] if close else None


def require_status(word):
    allowed = list(R.STATUSES)
    if word in allowed:
        return word
    near = nearest_status(word)
    hint = ' Nearest allowed status: %s.' % near if near else ''
    raise Fail(1, 'status "%s" is not one of: %s.%s' % (word, ', '.join(allowed), hint))


# --------------------------------------------------------------------------
# the change pipeline (R7.1, R4.13 - R4.17)
# --------------------------------------------------------------------------

def readme_text(manifest):
    rows = []
    fp = manifest.get('full_progress_artifact') or {}
    arts = ([fp] if fp else []) + [e for e in manifest.get('feature_artifacts', []) if isinstance(e, dict)]
    for e in arts:
        rows.append('| %s | `%s` | %s |' % (e.get('title', ''), e.get('file', ''), e.get('url') or '(not published)'))
    table = '\n'.join(['| Artifact | File | URL |', '|---|---|---|'] + rows)
    return (
        '# Project artifacts\n\n'
        'This folder is the record of %s\'s project artifacts (%s). It is generated and committed by\n'
        '`scripts/project_artifacts.py` of the `luismc-artifacts` plugin; do not edit the JSON or the\n'
        'rendered HTML by hand.\n\n'
        '%s\n\n'
        '## Recreate an artifact that was deleted on claude.ai\n\n'
        'The artifacts are disposable views; the record here is the source (R9.3).\n\n'
        '1. `python <plugin>/scripts/project_artifacts.py render` writes the HTML again from `content/`,\n'
        '   `registry.json` and `manifest.json`.\n'
        '2. `python <plugin>/scripts/project_artifacts.py pending` lists what must be published.\n'
        '3. Publish each listed file with the Artifact tool, to the URL in `manifest.json` when it still\n'
        '   opens. When the publish is refused because the artifact no longer exists, list your artifacts:\n'
        '   if one has the same title, publish to that one; only if none does, publish a new one.\n'
        '   At most one artifact per title is ever created.\n'
        '4. `python <plugin>/scripts/project_artifacts.py mark-published KEY --url URL` records the URL\n'
        '   and the hash of what was published.\n\n'
        'Change a task only with `set-task-status`; edit prose only under `content/<key>/` and then run\n'
        '`edit-content <key>`.\n' % (manifest.get('project', 'the project'), SPEC, table))


def run_change(ctx, apply, new_ok=False):
    """sync -> validate -> apply -> render -> validate -> commit -> push, with R4.15 retries."""
    with locked(ctx):
        retries = 0
        while True:
            ctx.attempt = retries + 1
            sync(ctx, create=new_ok)
            base = head_sha(ctx)
            if (ctx.record_dir / 'manifest.json').is_file():
                rec = Record.load(ctx.record_dir)
                mb = rec.manifest.get('default_branch')
                if isinstance(mb, str) and mb and mb != ctx.branch:
                    ctx.branch = mb
                    continue
                pre = validate_structure(rec)
                if pre:
                    raise Fail(1, 'the record is invalid; nothing written', pre)
            else:
                if not new_ok:
                    raise no_record_fail(ctx)
                rec = Record(ctx.record_dir, exists=False)
            try:
                result = apply(rec) or {}
                result = finish_change(ctx, rec, result)
            except BaseException:
                clean_worktree(ctx, base)
                raise
            sha = commit_record(ctx, rec.message or 'docs/artifacts: update')
            result['commit'] = sha or head_sha(ctx)
            result['pushed'] = False
            if sha is None:
                result['changed'] = False
                return result
            result['changed'] = True
            if ctx.no_push:
                return result
            out = push(ctx)
            if out == 'ok':
                result['pushed'] = True
                return result
            if out == 'refused':
                raise refused_fail(ctx)
            if out == 'race':
                clean_worktree(ctx, base)
                fetch(ctx, tolerant=True)
                retries += 1
                if retries > PUSH_RETRIES:
                    raise race_fail()
                continue
            raise Fail(1, 'git push failed: %s' % out[1])


def finish_change(ctx, rec, result):
    """Write manifest/registry, render, README; validate the result (R7.1)."""
    if getattr(rec, 'noop', False):
        result['rendered'] = []
        return result
    rec.sort_tasks()
    if rec.registry_changed() and rec.entry(FP_NAME) is not None:
        rec.render_keys.setdefault(FP_NAME, 'new')     # it embeds the registry (R5.9)
    rec.touch()
    now = rec.now()
    write_text(rec.dir / 'manifest.json', dump_json(rec.manifest))
    write_text(rec.dir / 'registry.json', dump_json(rec.registry))
    rec.invalidate()
    for key in sorted(rec.render_keys, key=lambda k: (k != FP_NAME, k)):
        rec.write_html(key, render_one(rec, key, now.text, now.iso))
    write_text(rec.dir / 'README.md', readme_text(rec.manifest))
    post = validate_structure(rec)
    for key in sorted(rec.rendered):
        post += check_html_findings(rec, key)
    if post:
        raise Fail(1, 'the change would make the record invalid; nothing written', sorted(set(post)))
    result['rendered'] = sorted(rec.rendered)
    result['stamp'] = now.iso
    return result


# --------------------------------------------------------------------------
# session checkout files (R10.2) and the rule copy note (R10.5)
# --------------------------------------------------------------------------

def install_session_files(root):
    """Extend .gitignore. Returns (changed paths, notes). The rule is not copied: the
    session-start hook delivers it (R10.4)."""
    changed, notes = [], []
    gi = Path(root) / '.gitignore'
    text = gi.read_text(encoding='utf-8') if gi.is_file() else ''
    have = {ln.strip().lstrip('/').rstrip('/') for ln in text.splitlines()}
    add = [ln for ln in GITIGNORE_LINES if ln.rstrip('/') not in have]
    if add:
        if text and not text.endswith('\n'):
            text += '\n'
        gi.write_bytes((text + '\n'.join(add) + '\n').encode('utf-8'))
        changed.append('.gitignore (added %s)' % ', '.join(add))
    return changed, notes


def session_report(changed, notes):
    lines = []
    if changed:
        lines.append('session checkout changes (commit these on your branch):')
        lines += ['  ' + c for c in changed]
    lines += ['note: ' + n for n in notes]
    return lines


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def slug_words(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def split_list(s):
    return [x.strip() for x in (s or '').split(',') if x.strip()]


def build_init(rec, args, project, root):
    """Fill a new Record with the manifest, registry and the full-progress content."""
    iana, win = local_zone_guess()
    zone = args.timezone or iana
    if not zone:
        warn('cannot tell the machine\'s time zone; using UTC (pass --timezone)')
        zone = 'UTC'
    win = args.windows_timezone if args.windows_timezone is not None else (WINDOWS_ZONES.get(zone) or win or '')
    label = args.label or zone.split('/')[-1].replace('_', ' ')
    title = 'Full Progress: %s' % project
    rec.manifest = {
        'spec': SPEC, 'project': project, 'timezone': zone, 'timezone_label': label,
        'windows_timezone': win, 'design': 'default', 'default_branch': args.default_branch_final,
        'merged_status': 'Live',
        'full_progress_artifact': {'key': FP_NAME, 'title': title,
                                   'file': R.artifact_file('full-progress', title),
                                   'url': '', 'published_sha256': ''},
        'feature_artifacts': [],
        'project_prefixes': sorted(set(split_list(','.join(args.project_prefix or [])))),
        'updated': '',
    }
    rec.registry = {'spec': SPEC, 'updated': '', 'tasks': []}
    d = rec.dir / 'content' / FP_NAME
    write_text(d / 'meta.json', dump_json({
        'title': title, 'hero': 'Everything in flight on %s.' % project,
        'lede': 'No work is recorded yet.', 'extra_css': ''}))
    # section 1 of this artifact is generated (the feature list), so this renders as section 2
    write_text(d / '01-how-to-read-this.html',
               '<!-- title: How to read this -->\n'
               '<p>Every row of the checklist comes from the task registry; nothing here is typed by hand.</p>\n')
    rec.render_keys[FP_NAME] = 'new'
    rec.exists = True


def cmd_init(args):
    ctx = make_ctx(args)
    args.default_branch_final = ctx.branch
    project = args.project

    def apply(rec):
        if rec.exists:
            raise Fail(1, 'a manifest already exists; init refuses to overwrite it')
        build_init(rec, args, project, ctx.root)
        rec.message = 'docs/artifacts: init'
        return {'command': 'init', 'project': project}

    res = run_change(ctx, apply, new_ok=True)
    changed, notes = install_session_files(ctx.root)
    res['session_changes'], res['notes'] = changed, notes
    emit(args, res, ['initialised the artifact record for %s (%s)' % (project, short(res))] +
         session_report(changed, notes) + ['record worktree: %s' % ctx.record_dir])
    return 0


def short(res):
    s = (res.get('commit') or '')[:7]
    return ('commit %s%s' % (s, '' if res.get('pushed') else ', not pushed')) if res.get('changed') else 'unchanged'


def cmd_feature_new(args):
    ctx = make_ctx(args)
    args.default_branch_final = ctx.branch
    key, name, prefix = args.key, args.title.strip(), args.prefix
    if not KEY_RE.match(key) or key == FP_NAME:
        raise Fail(1, 'key must be lowercase letters, digits and hyphens (and not "%s")' % FP_NAME)
    if not PREFIX_RE.match(prefix):
        raise Fail(1, 'prefix must be 2 to 5 capital letters')
    if name.startswith('Feature: '):
        name = name[len('Feature: '):]
    if not name:
        raise Fail(1, 'title is empty')
    apps = split_list(args.apps)
    project = args.project

    def apply(rec):
        created = not rec.exists
        if created:
            if not project:
                raise Fail(1, 'there is no artifact record yet; feature-new runs init first, so --project is required')
            build_init(rec, args, project, ctx.root)
        m = rec.manifest
        if any(e.get('key') == key for e in m['feature_artifacts']):
            raise Fail(1, 'feature artifact "%s" already exists' % key)
        taken = [e.get('prefix') for e in m['feature_artifacts']] + list(m['project_prefixes'])
        if prefix in taken:
            raise Fail(1, 'prefix %s is already registered' % prefix)
        title = 'Feature: %s' % name
        m['feature_artifacts'].append({
            'key': key, 'title': title, 'url': '', 'file': R.artifact_file('feature', title),
            'prefix': prefix, 'apps': apps, 'published_sha256': ''})
        d = rec.dir / 'content' / key
        if d.exists():
            raise Fail(1, 'content/%s already exists' % key)
        now = rec.now()
        write_text(d / 'meta.json', dump_json({
            'title': title, 'hero': args.hero or 'Where %s stands.' % name,
            'lede': 'Planned. Work has not started.', 'extra_css': ''}))
        write_text(d / '01-what-and-why.html',
                   '<!-- title: What and why -->\n<p>Describe what this feature is and why it exists.</p>\n')
        write_text(d / 'history.json', dump_json([{'date': now.text, 'change': 'Feature artifact created.'}]))
        rec.render_keys[key] = 'new'
        rec.render_keys[FP_NAME] = 'new'
        rec.message = 'docs/artifacts: add feature %s' % key
        return {'command': 'feature-new', 'key': key, 'title': title, 'prefix': prefix,
                'file': m['feature_artifacts'][-1]['file'], 'initialised': created}

    res = run_change(ctx, apply, new_ok=True)
    changed, notes = install_session_files(ctx.root)
    res['session_changes'], res['notes'] = changed, notes
    emit(args, res, ['added feature artifact "%s" (%s)' % (key, short(res)),
                     'to edit its prose: export-content %s --to DIR, edit, edit-content %s --from DIR' % (key, key)] +
         session_report(changed, notes))
    return 0


def cmd_task_add(args):
    ctx = make_ctx(args)
    status = require_status(args.status)

    def apply(rec):
        m, reg = rec.manifest, rec.registry
        owner = args.owner
        feats = {e['key']: e for e in m['feature_artifacts']}
        pfx = args.prefix
        app = args.app
        if owner == 'project':
            pp = m['project_prefixes']
            if pfx is None:
                if len(pp) != 1:
                    raise Fail(1, 'give --prefix for a project task (project prefixes: %s)' % (', '.join(pp) or 'none'))
                pfx = pp[0]
            else:
                if not PREFIX_RE.match(pfx):
                    raise Fail(1, 'prefix must be 2 to 5 capital letters')
                if pfx in [e['prefix'] for e in feats.values()]:
                    raise Fail(1, 'prefix %s belongs to a feature artifact' % pfx)
                if pfx not in pp:
                    pp.append(pfx)
                    pp.sort()
            app = app or ''
        else:
            if owner not in feats:
                raise Fail(1, 'unknown owner "%s" (a feature key or project)' % owner)
            e = feats[owner]
            if pfx and pfx != e['prefix']:
                raise Fail(1, 'prefix %s is not the prefix of "%s" (%s)' % (pfx, owner, e['prefix']))
            pfx = e['prefix']
            if app is None:
                app = e['apps'][0] if len(e['apps']) == 1 else ''
        nums = [int(ID_RE.match(t['id']).group(2)) for t in rec.tasks()
                if ID_RE.match(str(t.get('id', ''))) and ID_RE.match(t['id']).group(1) == pfx]
        tid = '%s%d' % (pfx, max(nums, default=0) + 1)
        now = rec.now()
        reg['tasks'].append({'id': tid, 'owner': owner, 'app': app, 'status': status,
                             'item': args.item, 'detail': args.detail, 'expected': args.expected,
                             'changed': now.iso})
        if owner != 'project':
            rec.render_keys[owner] = 'new'
        rec.render_keys[FP_NAME] = 'new'
        rec.message = 'docs/artifacts: %s %s' % (tid, status)
        return {'command': 'task-add', 'id': tid, 'status': status}

    res = run_change(ctx, apply)
    emit(args, res, res['id'])
    if not args.json_out:
        print('project_artifacts: %s added (%s)' % (res['id'], short(res)), file=sys.stderr)
    return 0


def cmd_set_task_status(args):
    status = require_status(args.status)
    ctx = make_ctx(args)

    def apply(rec):
        task = next((t for t in rec.tasks() if t.get('id') == args.id), None)
        if task is None:
            raise Fail(1, 'unknown task ID "%s"' % args.id)
        now = rec.now()
        prev = task['status']
        task['status'] = status
        task['changed'] = now.iso
        if args.detail is not None:
            task['detail'] = args.detail
        if args.expected is not None:
            task['expected'] = args.expected
        elif status in ('Live', 'Done'):
            task['expected'] = now.date          # R6.8
        owner = task['owner']
        if owner != 'project':
            rec.render_keys[owner] = 'new'
            if args.history:
                hp = rec.dir / 'content' / owner / 'history.json'
                try:
                    hist = json.loads(hp.read_text(encoding='utf-8')) if hp.is_file() else []
                except ValueError:
                    raise Fail(1, 'content/%s/history.json is not valid JSON' % owner)
                hist.insert(0, {'date': now.text, 'change': args.history})
                write_text(hp, dump_json(hist))
                rec.invalidate()
        elif args.history:
            warn('%s is a project task; project tasks have no History, --history ignored' % args.id)
        rec.render_keys[FP_NAME] = 'new'
        rec.message = 'docs/artifacts: %s %s' % (args.id, status)
        return {'command': 'set-task-status', 'id': args.id, 'status': status, 'previous': prev,
                'expected': task['expected']}

    res = run_change(ctx, apply)
    removed = 0
    if artifact_queue.read_queue(str(ctx.root)) and any(
            e.get('id') == args.id for e in artifact_queue.read_queue(str(ctx.root))):
        removed = len([e for e in artifact_queue.read_queue(str(ctx.root)) if e.get('id') == args.id])
        artifact_queue.remove_events(str(ctx.root), args.id)
    res['removed_events'] = removed
    emit(args, res, '%s %s -> %s (%s)' % (res['id'], res['previous'], res['status'], short(res)))
    return 0


def content_files(d):
    """{name: bytes} of the regular files directly in a content folder; refuses anything else."""
    d = Path(d)
    if not d.is_dir():
        raise Fail(1, '%s is not a folder' % d)
    out = {}
    for p in sorted(d.iterdir()):
        if not p.is_file():
            raise Fail(1, '%s: content folders hold files only, found %s' % (d, p.name))
        out[p.name] = p.read_bytes()
    return out


def cmd_export_content(args):
    key = args.key
    if not KEY_RE.match(key):
        raise Fail(1, 'key must be lowercase letters, digits and hyphens')
    _ctx, rec = load_for_read(args)
    if rec.entry(key) is None:
        raise Fail(1, 'unknown artifact key "%s"' % key)
    src = rec.dir / 'content' / key
    if not src.is_dir():
        raise Fail(2, 'content/%s is missing from the record' % key)
    dest = Path(args.to)
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise Fail(1, '%s exists and is not an empty folder' % dest)
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    for name, data in content_files(src).items():
        (dest / name).write_bytes(data)
        names.append(name)
    emit(args, {'command': 'export-content', 'key': key, 'to': str(dest), 'files': names},
         'exported %d file(s) of %s to %s' % (len(names), key, dest))
    return 0


def cmd_edit_content(args):
    ctx = make_ctx(args)
    key = args.key
    if not KEY_RE.match(key):
        raise Fail(1, 'key must be lowercase letters, digits and hyphens')
    src = content_files(args.from_dir)       # read once; a retried push re-applies the same files

    def apply(rec):
        if rec.entry(key) is None:
            raise Fail(1, 'unknown artifact key "%s"' % key)
        d = rec.dir / 'content' / key
        new = {n: b.replace(b'\r\n', b'\n') for n, b in src.items()}
        if d.is_dir() and new == content_files(d):
            rec.noop = True
            return {'command': 'edit-content', 'key': key, 'files': sorted(src), 'no_change': True}
        if d.exists():
            shutil.rmtree(str(d))
        d.mkdir(parents=True)
        for name, data in src.items():
            (d / name).write_bytes(data.replace(b'\r\n', b'\n'))
        rec.invalidate()
        rec.contents()                       # validates what the session supplied
        rec.render_keys[key] = 'new'
        if key != FP_NAME:
            rec.render_keys[FP_NAME] = 'new'   # section 1 quotes each lede
        rec.message = 'docs/artifacts: edit %s' % key
        return {'command': 'edit-content', 'key': key, 'files': sorted(src)}

    res = run_change(ctx, apply)
    emit(args, res, 'edit-content %s: %s' % (key, 'no change' if res.get('no_change') else short(res)))
    return 0


def cmd_design(args):
    ctx = make_ctx(args)
    target = args.target
    css = None
    if target != 'default':
        f = Path(target)
        if not f.is_file():
            raise Fail(1, 'design file %s does not exist' % f)
        css = f.read_bytes().decode('utf-8-sig').replace('\r\n', '\n')
        check = getattr(R, 'check_tokens', None)
        problems = check(css) if check else []
        if problems:
            raise Fail(1, '%s does not satisfy the token contract; nothing written' % f,
                       [('R5.11', f.name, p) for p in problems])

    def apply(rec):
        dpath = rec.dir / 'design.css'
        if css is None:
            if rec.manifest.get('design') == 'default' and not dpath.exists():
                rec.noop = True
                return {'command': 'design', 'design': 'default'}
            if dpath.exists():
                dpath.unlink()
            rec.manifest['design'] = 'default'
        else:
            old = read_html(dpath)
            if rec.manifest.get('design') == 'design.css' and old == css:
                rec.noop = True
                return {'command': 'design', 'design': 'design.css'}
            write_text(dpath, css)
            rec.manifest['design'] = 'design.css'
        for key, _kind, _e in rec.artifacts():     # every artifact carries the token block
            rec.render_keys[key] = 'new'
        rec.message = 'docs/artifacts: design %s' % ('default' if css is None else 'design.css')
        return {'command': 'design', 'design': rec.manifest['design']}

    res = run_change(ctx, apply)
    emit(args, res, 'design: %s (%s)' % (res['design'], short(res)))
    return 0


def cmd_render(args):
    ctx = make_ctx(args)

    def apply(rec):
        now = rec.now()
        for key, _kind, e in rec.artifacts():
            old = read_html(rec.dir / e['file'])
            if args.all or old is None:
                rec.render_keys[key] = 'new'
                continue
            st = existing_stamp(old)
            if st is None or render_one(rec, key, stamp_text_from_iso(st), st).replace('\r\n', '\n') != old:
                rec.render_keys[key] = 'new'
        rec.message = 'docs/artifacts: render'
        rec.noop = not rec.render_keys
        return {'command': 'render'}

    res = run_change(ctx, apply)
    emit(args, res, ['rendered: ' + (', '.join(res['rendered']) or 'nothing to do')])
    return 0


def cmd_mark_published(args):
    ctx = make_ctx(args)
    key, url = args.key, args.url
    if not re.match(r'^https?://\S+$', url):
        raise Fail(1, 'url must be an http(s) URL')

    def apply(rec):
        e = rec.entry(key)
        if e is None:
            raise Fail(1, 'unknown artifact key "%s"' % key)
        old = read_html(rec.dir / e['file'])
        st = existing_stamp(old)
        if old is None or st is None:
            raise Fail(1, '%s has not been rendered; run render first' % e['file'])
        if render_one(rec, key, stamp_text_from_iso(st), st).replace('\r\n', '\n') != old:
            raise Fail(1, '%s differs from a fresh render; run render first' % e['file'])
        e['url'] = url
        rec.invalidate()
        # other artifacts may link to this url; refresh them keeping their stamps
        stale = rerender_existing(rec)
        e['published_sha256'] = sha_of_file(rec.html_path(key))
        rec.message = 'docs/artifacts: published %s' % key
        return {'command': 'mark-published', 'key': key, 'url': url,
                'sha256': e['published_sha256'], 'refreshed': sorted(k for k in stale if k != key)}

    res = run_change(ctx, apply)
    emit(args, res, 'recorded %s -> %s (%s)' % (key, url, short(res)))
    return 0


def cmd_commit(args):
    ctx = make_ctx(args)
    with locked(ctx):
        ensure_worktree(ctx)
        dirty = dirty_paths(ctx)
        sha = None
        if dirty:
            if args.retry:
                raise Fail(1, 'the record worktree has uncommitted edits; run commit without --retry')
            rec = Record.load(ctx.record_dir)
            findings = validate_structure(rec)
            if findings:
                raise Fail(1, 'the record is invalid; nothing committed', findings)
            sha = commit_record(ctx, args.message or 'docs/artifacts: update')
        if not ahead_count(ctx):
            emit(args, {'command': 'commit', 'changed': False, 'pushed': False}, 'nothing to commit or push')
            return 0
        if args.no_push:
            emit(args, {'command': 'commit', 'changed': True, 'pushed': False, 'commit': head_sha(ctx)},
                 'committed %s, not pushed' % head_sha(ctx)[:7])
            return 0
        retries = 0
        while True:
            ctx.attempt = retries + 1
            out = push(ctx)
            if out == 'ok':
                break
            if out == 'refused':
                raise refused_fail(ctx)
            if out == 'race':
                retries += 1
                if retries > PUSH_RETRIES:
                    raise Fail(3, 'record push lost the race %d times' % (PUSH_RETRIES + 1))
                fetch(ctx)
                r = git(ctx.wt, 'rebase', '--quiet', 'origin/' + ctx.branch)
                if r.returncode != 0:
                    git(ctx.wt, 'rebase', '--abort')
                    raise Fail(2, 'cannot rebase the record commit onto origin/%s' % ctx.branch)
                continue
            raise Fail(1, 'git push failed: %s' % out[1])
    emit(args, {'command': 'commit', 'changed': True, 'pushed': True, 'commit': head_sha(ctx)},
         'pushed %s to %s' % (head_sha(ctx)[:7], ctx.branch))
    return 0


def load_for_read(args):
    """Return (ctx, Record or None) for a read-only command, from the synced record worktree."""
    ctx = make_ctx(args)
    with locked(ctx):
        sync(ctx, readonly=True)
    if not (ctx.record_dir / 'manifest.json').is_file():
        raise no_record_fail(ctx)
    rec = Record.load(ctx.record_dir)
    mb = rec.manifest.get('default_branch')
    if isinstance(mb, str) and mb and mb != ctx.branch:
        ctx.branch = mb
        with locked(ctx):
            sync(ctx, readonly=True)
        rec = Record.load(ctx.record_dir)
    return ctx, rec


def rule_copy_notes():
    """A note (never a finding) when the project keeps its own, differing copy of the rule (R10.5)."""
    root = session_root() if artifact_queue is not None else None
    src = PLUGIN_DIR / 'rules' / RULE_NAME
    dst = Path(root) / '.claude' / 'rules' / RULE_NAME if root else None
    try:
        if dst is not None and dst.is_file() and src.is_file() and dst.read_bytes() != src.read_bytes():
            return ['.claude/rules/%s differs from the plugin\'s rules/%s; the plugin now delivers the rule '
                    'at session start, so this copy can be deleted' % (RULE_NAME, RULE_NAME)]
    except OSError:
        pass
    return []


def cmd_check(args):
    if R is None:
        raise Fail(2, 'render_artifacts.py cannot be imported: %s' % _RENDER_ERROR)
    if args.record:
        d = Path(args.record)
        if (d / RECORD_REL / 'manifest.json').is_file():
            d = d / RECORD_REL
        rec = Record.load(d)
    else:
        _ctx, rec = load_for_read(args)
    findings = validate_structure(rec)
    for key, _kind, e in rec.artifacts():
        if not isinstance(key, str) or not KEY_RE.match(key) or not isinstance(e.get('file'), str):
            continue
        findings += check_html_findings(rec, key)
        findings += fresh_render_findings(rec, key)
    findings = sorted(set(findings))
    if getattr(args, 'json_out', False):
        print(json.dumps({'findings': [{'req': r, 'file': f, 'message': m} for r, f, m in findings]},
                         indent=2, ensure_ascii=False))
    elif findings:
        print('\n'.join(fmt_finding(x) for x in findings))
    else:
        print('record is clean')
    return 1 if findings else 0


def cmd_pending(args):
    ctx, rec = load_for_read(args)
    arts = []
    if rec is not None:
        for key, _kind, e in rec.artifacts():
            p = rec.dir / str(e.get('file', ''))
            if not p.is_file():
                reason = 'not rendered yet; run render'
            else:
                h = sha_of_file(p)
                if not e.get('published_sha256') and not e.get('url'):
                    reason = 'never published'
                elif e.get('url') and not e.get('published_sha256'):
                    reason = 'adopted, not yet published from the record'
                elif h != e.get('published_sha256'):
                    reason = 'changed since last publish'
                else:
                    continue
            arts.append({'key': key, 'title': e.get('title', ''), 'file': e.get('file', ''), 'path': str(p),
                         'url': e.get('url', ''), 'reason': reason})
    queue = artifact_queue.read_queue(str(ctx.root))
    if args.json_out:
        print(json.dumps({'artifacts': arts, 'queue': queue}, indent=2, ensure_ascii=False))
    else:
        for a in arts:
            print('publish %s (%s): %s%s' % (a['key'], a['path'], a['reason'],
                                             '' if a['url'] else ' [no URL yet]'))
        for ev in queue:
            print('queued %s -> %s (%s)' % (ev.get('id'), ev.get('suggested_status'), ev.get('event')))
        if not arts and not queue:
            print('nothing pending')
    return 1 if (arts or queue) else 0


def cmd_queue(args):
    if artifact_queue is None:
        raise Fail(2, 'artifact_queue.py cannot be imported: %s' % _QUEUE_ERROR)
    root = session_root()
    if not root:
        raise Fail(2, 'not inside a git repository')
    if args.action == 'list':
        events = artifact_queue.read_queue(root)
        if args.id:
            events = [e for e in events if e.get('id') == args.id]
        if args.json_out:
            print(json.dumps({'queue': events}, indent=2, ensure_ascii=False))
        else:
            for ev in events:
                print('%s -> %s (%s)' % (ev.get('id'), ev.get('suggested_status'), ev.get('event')))
            if not events:
                print('queue is empty')
    else:
        before = len(artifact_queue.read_queue(root))
        if before:
            artifact_queue.remove_events(root, args.id)
        after = len(artifact_queue.read_queue(root))
        emit(args, {'removed': before - after}, 'removed %d queued event(s)' % (before - after))
    return 0


def cmd_path(args):
    ctx, _rec = load_for_read(args)
    emit(args, {'record_dir': str(ctx.record_dir), 'worktree': str(ctx.wt)}, str(ctx.record_dir))
    return 0


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------

def build_parser():
    j = argparse.ArgumentParser(add_help=False)
    j.add_argument('--json', dest='json_out', action='store_true', help='machine-readable output')
    w = argparse.ArgumentParser(add_help=False, parents=[j])
    w.add_argument('--no-push', action='store_true', help='commit in the record worktree, do not push')

    p = argparse.ArgumentParser(prog='project_artifacts.py', description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='command', required=True, metavar='command')

    def init_opts(s):
        s.add_argument('--timezone')
        s.add_argument('--label')
        s.add_argument('--windows-timezone')
        s.add_argument('--default-branch')
        s.add_argument('--project-prefix', action='append',
                       help='a prefix owned by the project (repeatable or comma separated)')

    s = sub.add_parser('init', parents=[w], help='create the manifest, registry and full-progress content')
    s.add_argument('--project', required=True)
    init_opts(s)
    s.set_defaults(func=cmd_init)

    s = sub.add_parser('feature-new', parents=[w], help='add a feature artifact (runs init when needed)')
    s.add_argument('--key', required=True)
    s.add_argument('--title', required=True)
    s.add_argument('--prefix', required=True)
    s.add_argument('--apps', required=True)
    s.add_argument('--hero')
    s.add_argument('--project', help='project name when init runs first (default: the repository name)')
    init_opts(s)
    s.set_defaults(func=cmd_feature_new)

    s = sub.add_parser('task-add', parents=[w], help='add a task; prints its ID')
    s.add_argument('--owner', required=True, help='a feature key, or project')
    s.add_argument('--item', required=True)
    s.add_argument('--detail', required=True)
    s.add_argument('--expected', required=True)
    s.add_argument('--app')
    s.add_argument('--status', default='To do')
    s.add_argument('--prefix')
    s.set_defaults(func=cmd_task_add)

    s = sub.add_parser('set-task-status', parents=[w], help='change one task')
    s.add_argument('id')
    s.add_argument('status')
    s.add_argument('--detail')
    s.add_argument('--expected')
    s.add_argument('--history')
    s.set_defaults(func=cmd_set_task_status)

    s = sub.add_parser('export-content', parents=[j], help="copy an artifact's content files out of the record")
    s.add_argument('key')
    s.add_argument('--to', required=True, metavar='DIR')
    s.set_defaults(func=cmd_export_content)

    s = sub.add_parser('edit-content', parents=[w], help="replace an artifact's content files with a folder's")
    s.add_argument('key')
    s.add_argument('--from', dest='from_dir', required=True, metavar='DIR')
    s.set_defaults(func=cmd_edit_content)

    s = sub.add_parser('design', parents=[w], help="set the project's design tokens, or go back to the default")
    s.add_argument('action', choices=['set'])
    s.add_argument('target', metavar='FILE|default')
    s.set_defaults(func=cmd_design)

    s = sub.add_parser('render', parents=[w], help='render every artifact whose output would change')
    s.add_argument('--all', action='store_true')
    s.set_defaults(func=cmd_render)

    s = sub.add_parser('check', parents=[j], help='the conformance checks of section 14')
    s.add_argument('--record', help='a docs/artifacts folder (or the repository containing it)')
    s.set_defaults(func=cmd_check)

    s = sub.add_parser('pending', parents=[j], help='artifacts to publish and queued events; exit 1 when any')
    s.set_defaults(func=cmd_pending)

    s = sub.add_parser('mark-published', parents=[w], help='record the URL and hash of what was published')
    s.add_argument('key')
    s.add_argument('--url', required=True)
    s.set_defaults(func=cmd_mark_published)

    s = sub.add_parser('queue', parents=[j], help='show or clear queued events')
    s.add_argument('action', choices=['list', 'clear'])
    s.add_argument('--id')
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser('commit', parents=[w], help='commit and push the record (also done by every writing command)')
    s.add_argument('--retry', action='store_true', help='push a commit kept after a refused push')
    s.add_argument('--message')
    s.set_defaults(func=cmd_commit)

    s = sub.add_parser('path', parents=[j], help='print the record folder inside the record worktree')
    s.set_defaults(func=cmd_path)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except (OSError, ValueError):
                pass
    args = build_parser().parse_args(argv)
    if not hasattr(args, 'no_push'):
        args.no_push = False
    try:
        if R is None and args.command != 'queue':
            raise Fail(2, 'render_artifacts.py cannot be imported: %s' % _RENDER_ERROR)
        return args.func(args) or 0
    except Fail as e:
        if getattr(args, 'json_out', False):
            print(json.dumps({'ok': False, 'exit': e.code, 'error': e.msg,
                              'findings': [{'req': r, 'file': f, 'message': m} for r, f, m in e.findings]},
                             indent=2, ensure_ascii=False))
        for fd in e.findings:
            print(fmt_finding(fd), file=sys.stderr)
        print('project_artifacts: %s (exit %d)' % (e.msg, e.code), file=sys.stderr)
        return e.code


if __name__ == '__main__':
    sys.exit(main())
