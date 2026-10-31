#!/usr/bin/env python3
"""project_artifacts.py - the only writer of a project's artifact record.

Implements ARTIFACTSPEC 1.10.0: section 4 (the record, time, the record in the
working tree; the plugin writes files and never commits or pushes), section 7 (every command), the bookkeeping of
section 9 (`pending`, `mark-published`; only Full Progress is published, a
feature artifact is a standalone file) and the record-level checks of
section 14. Rendering lives in render_artifacts.py, the queue in
artifact_queue.py. Python 3.10+, standard library only.

Exit codes: 0 success, 1 findings or a refused action, 2 unreadable record
(or a broken environment). Exit codes 3 and 4 are no longer used.
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
    import artifact_promote as PROMOTE
except ImportError as _e:  # pragma: no cover - broken install
    PROMOTE = None
    _PROMOTE_ERROR = str(_e)
try:
    import artifact_retire as AR
except ImportError as _e:  # pragma: no cover - broken install
    AR = None
    _RETIRE_ERROR = str(_e)
try:
    import artifact_hourly as H
except ImportError as _e:  # pragma: no cover - broken install
    H = None
    _HOURLY_ERROR = str(_e)
try:
    import render_artifacts as R
except ImportError as _e:
    R = None
    _RENDER_ERROR = str(_e)

SPEC = 'ARTIFACTSPEC 1.0.0'
FP_NAME = 'full-progress'
RECORD_REL = 'docs/artifacts'       # the default; the project's record_dir setting overrides it (current_rel)
WAITS_ON = ('owner', 'work')   # R5.34a: who a Waiting or On hold task waits on; absent means work
BASIS_MAX = 80            # R6.10: longest Expected basis
OPEN_STATUSES = ('Running', 'Waiting', 'To do', 'Needs you', 'On hold')     # R6.6
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
KEY_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
PREFIX_RE = re.compile(r'^[A-Z]{2,5}$')
ID_RE = re.compile(r'^([A-Z]{2,5})([1-9][0-9]*)$')
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
EXPECTED_RE = re.compile(
    r'^(0[1-9]|[12][0-9]|3[01]) (?:' + '|'.join(MONTHS) + r')( ~([01][0-9]|2[0-3]):[0-5][0-9])?(; \S.*)?$')
TIME_EL_RE = re.compile(r'<time\b[^>]*\bdatetime="([^"]+)"')
RULE_NAME = 'project-artifacts.md'
STALE_RULE_REL = '.claude/rules/project-artifacts.md'     # the copy 1.0.0 `init` made (R10.6)
PUBLISH_REL = os.path.join('.claude', 'artifacts-publish')      # the publish copy of Full Progress (R5.31)
GITIGNORE_LINES = ['.claude/artifacts-queue.json', '.claude/artifacts-stop-state.json', '.claude/artifacts-publish/',
                   '.claude/artifacts-local.json', '.claude/artifacts-record.lock', '.claude/worktrees/']


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
        for n in (result or {}).get('notes') or []:
            print('note: ' + n)


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
# git (read-only) and the record in the working tree (R4.13 - R4.17)
# --------------------------------------------------------------------------

READ_ONLY_GIT = ('rev-parse', 'symbolic-ref', 'status', 'diff', 'log', 'show', 'ls-files', 'config', 'worktree')


def git(cwd, *a, check=False, ok=(0,)):
    """Run a read-only git command (R4.13). The plugin never writes git state: anything else is refused."""
    sub = a[0] if a else ''
    if sub not in READ_ONLY_GIT or (sub == 'config' and '--get' not in a) or (sub == 'worktree' and a[1:2] != ('list',)):
        raise Fail(2, 'refusing to run git %s: the plugin never writes git state (ARTIFACTSPEC 1.8.0)' % ' '.join(a[:2]))
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
    """The top of the working tree (R4.13). Inside an old record worktree it leads back to the checkout."""
    top = artifact_queue.repo_root(start)
    if not top:
        return None
    norm = top.replace('\\', '/')
    tail = '/.claude/worktrees/artifacts-record'
    if norm.endswith(tail):
        return norm[:-len(tail)]
    return top


def record_rel_or_fail(root):
    """The record folder of the project (record_dir in .claude/artifacts.json, else docs/artifacts)."""
    if artifact_queue is None:
        raise Fail(2, 'artifact_queue.py cannot be imported: %s' % _QUEUE_ERROR)
    try:
        return artifact_queue.record_rel(str(root))
    except artifact_queue.RecordDirError as e:
        raise Fail(2, str(e))


def current_rel(root=None):
    """The record folder for messages: never raises, falls back to the default."""
    root = root or session_root()
    if artifact_queue is None or not root:
        return RECORD_REL
    return artifact_queue.record_rel_safe(str(root))


class Ctx:
    def __init__(self, root, branch):
        self.root = Path(root)
        self.branch = branch
        self.rel = record_rel_or_fail(self.root)
        self.record_dir = self.root / self.rel
        self.wt = self.root          # the record lives in the working tree; the record worktree is retired (R4.24)


def detect_default_branch(root, given=None):
    """Only recorded in a new manifest; read-only: origin/HEAD, origin/main|master, else the current branch."""
    if given:
        return given
    ref = git_out(root, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD')
    if ref and ref.startswith('origin/'):
        return ref[len('origin/'):]
    for b in ('main', 'master'):
        if git(root, 'rev-parse', '--verify', '-q', 'refs/remotes/origin/' + b).returncode == 0:
            return b
    return git_out(root, 'symbolic-ref', '--short', '-q', 'HEAD') or 'main'


NO_COMMIT_MSG = 'the plugin no longer commits or pushes (ARTIFACTSPEC 1.8.0); commit %s/ when you choose'


def make_ctx(args, branch=None):
    if artifact_queue is None:
        raise Fail(2, 'artifact_queue.py cannot be imported: %s' % _QUEUE_ERROR)
    root = session_root()
    if not root:
        raise Fail(2, 'not inside a git repository')
    if getattr(args, 'push', False):
        print('luismc-artifacts: ' + NO_COMMIT_MSG % current_rel(root), file=sys.stderr)       # R4.28: --push does nothing
    return Ctx(root, branch or detect_default_branch(root, getattr(args, 'default_branch', None)))


LOCK_REL = os.path.join('.claude', 'artifacts-record.lock')       # outside docs/artifacts/, a git-ignored path (R4.17)


@contextlib.contextmanager
def locked(ctx):
    p = ctx.root / LOCK_REL
    p.parent.mkdir(parents=True, exist_ok=True)
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
                raise Fail(1, 'the record is locked by another invocation (%s)' % p)
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            p.unlink()
        except OSError:
            pass


def no_record_fail(ctx):
    return Fail(2, 'no record in this repository (no %s/manifest.json); run init' % ctx.rel)


def snapshot(ctx):
    """{relative path: bytes} of every file under the record folder, to put back when a change fails."""
    out = {}
    d = ctx.record_dir
    if d.is_dir():
        for p in d.rglob('*'):
            if p.is_file():
                out[p.relative_to(d).as_posix()] = p.read_bytes()
    return out


def restore(ctx, snap):
    d = ctx.record_dir
    if d.is_dir():
        for p in sorted(d.rglob('*'), key=lambda x: len(x.parts), reverse=True):
            if p.is_file() and p.relative_to(d).as_posix() not in snap:
                p.unlink()
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    for rel, data in snap.items():
        p = d / rel
        if not p.is_file() or p.read_bytes() != data:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)


# --- migration of the old record worktree (R4.24, AR50 rule 4) ---------------

def old_record_worktree(root):
    """Where the retired record worktree was: the old setting if it is usable, else the default path."""
    try:
        return artifact_queue.record_worktree(str(root))
    except artifact_queue.WorktreeSettingError:
        return artifact_queue.default_worktree(str(root))


def newest_stamp(record_dir):
    """The registry's newest `changed` stamp (or its `updated`) as a datetime, or None."""
    try:
        reg = json.loads((Path(record_dir) / 'registry.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(reg, dict) or not isinstance(reg.get('tasks', []), list):
        return None
    stamps = [t.get('changed') for t in reg.get('tasks', []) if isinstance(t, dict)] + [reg.get('updated')]
    parsed = [parse_iso(s) for s in stamps if isinstance(s, str)]
    parsed = [x for x in parsed if x is not None]
    return max(parsed) if parsed else None


def migrate_record(ctx):
    """Copy the old record worktree's docs/artifacts/ into the working tree when its registry is newer.
    Returns the one-line note when it copied, else None. Idempotent; never runs a git write."""
    old = Path(old_record_worktree(ctx.root))
    old_dir = old / RECORD_REL      # the old worktree always held docs/artifacts
    if artifact_queue._same_path(str(old), str(ctx.root)) or not (old_dir / 'registry.json').is_file():
        return None
    theirs, mine = newest_stamp(old_dir), newest_stamp(ctx.record_dir)
    if theirs is None or (mine is not None and theirs <= mine):
        return None
    for p in old_dir.rglob('*'):
        if p.is_file():
            dest = ctx.record_dir / p.relative_to(old_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(p), str(dest))
    return ('luismc-artifacts: the record now lives in %s/ and is never committed or pushed by the '
            'plugin; copied it from %s. You may remove that worktree with git worktree remove %s' % (ctx.rel, old, old))


def migrate_quietly(ctx):
    """The implicit run before a writing command: the note goes to stderr."""
    note = migrate_record(ctx)
    if note:
        print(note, file=sys.stderr)
    return note


def setting_ignored_notes(root):
    """check says once, as info, that the old worktree setting is ignored (R4.24)."""
    used = bool(os.environ.get(artifact_queue.WORKTREE_ENV))
    p = Path(root) / artifact_queue.LOCAL_NAME
    try:
        if p.is_file() and 'record_worktree' in json.loads(p.read_text(encoding='utf-8')):
            used = True
    except (OSError, ValueError, TypeError):
        pass
    if not used:
        return []
    return ['%s and record_worktree in %s are ignored since ARTIFACTSPEC 1.8.0: the record lives in %s/ '
            'of the working tree' % (artifact_queue.WORKTREE_ENV, artifact_queue.LOCAL_NAME.replace(os.sep, '/'),
                                     current_rel(root))]


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


def migrate_done(manifest, registry):
    """Read the status Done, retired in 1.1.0, as Built (in tasks and in merged_status).
    Returns (IDs of tasks changed, whether anything changed); the next writing command writes it."""
    ids = []
    tasks = registry.get('tasks')
    for t in tasks if isinstance(tasks, list) else []:
        if isinstance(t, dict) and t.get('status') == 'Done':
            t['status'] = 'Built'
            ids.append(str(t.get('id')))
    merged = manifest.get('merged_status') == 'Done'
    if merged:
        manifest['merged_status'] = 'Built'
    return ids, bool(ids) or merged


def release_number(task):
    """R5.45: the number of a release row (a positive whole number), else None."""
    n = task.get('release') if isinstance(task, dict) else None
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else None


def is_release(task):
    """R5.40: a release row; an older `"release": true` still counts until the migration numbers it."""
    return isinstance(task, dict) and (task.get('release') is True or release_number(task) is not None)


def next_release_number(tasks):
    return max([release_number(t) or 0 for t in tasks if isinstance(t, dict)], default=0) + 1


def migrate_releases(registry):
    """R5.45: number the rows that still say `"release": true`, oldest `changed` first, ties by ID, after the
    highest number in use. Returns the IDs numbered; the next writing command writes them."""
    tasks = registry.get('tasks')
    tasks = tasks if isinstance(tasks, list) else []
    old = [t for t in tasks if isinstance(t, dict) and t.get('release') is True]
    floor = datetime.min.replace(tzinfo=timezone.utc)
    n = next_release_number(tasks)
    ids = []
    for t in sorted(old, key=lambda t: (parse_iso(t.get('changed')) or floor, task_sort_key(t))):
        t['release'] = n
        n += 1
        ids.append(str(t.get('id')))
    return ids


class Record:
    def __init__(self, d, manifest=None, registry=None, exists=True):
        self.dir = Path(d)
        self.manifest = manifest
        self.registry = registry
        self._tasks0 = (copy.deepcopy(self.tasks()) if isinstance(registry, dict) else None)
        self.exists = exists
        self._now = None
        self._contents = None
        self._broken = {}            # key -> content findings (R4.4, R4.10, ...) of an artifact that cannot load
        self._partial = {}           # key -> what could be read of such an artifact (its lede, for Full Progress)
        self.pre_findings = []       # the findings the record had before this change (R7.1)
        self.skipped = []            # artifacts left as they are because their content is invalid (R7.1a)
        self.render_keys = {}        # key -> 'new': render with a new stamp
        self.rendered = set()
        self.message = None
        self.old_done = []           # IDs read from the file with the retired status Done
        self.old_merged = False      # merged_status read from the file as the retired Done
        self.old_urls = []           # feature keys read from the file with a url (R4.18)
        self.old_releases = []       # IDs read from the file with "release": true, numbered on load (R5.45)
        self.migrated = False
        self.recovered = 0           # retired pages added from the history of manifest.json (R4.20)

    @property
    def retired_changed(self):
        return bool(self.recovered)

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
        raw_tasks = copy.deepcopy(registry.get('tasks')) if isinstance(registry.get('tasks'), list) else None
        old_merged = manifest.get('merged_status') == 'Done'
        old_done, migrated = migrate_done(manifest, registry)
        old_releases = migrate_releases(registry)
        migrated = migrated or bool(old_releases)
        rec = cls(d, manifest, registry)
        iso = lambda: rec.now().iso      # noqa: E731 - read only when something is retired
        old_urls = AR.move_feature_urls(manifest, iso) if AR else []         # R4.18, R4.19
        rec.recovered = AR.recover_retired(manifest, d, iso) if AR else 0    # R4.20
        if migrated:
            rec._tasks0 = raw_tasks      # the registry differs from the file, so it is rewritten
            rec.old_done, rec.old_merged = old_done, old_merged
            rec.old_releases = old_releases
        if migrated or old_urls:
            rec.migrated = True
            rec.old_urls = old_urls
        return rec

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

    def _load(self):
        if self._contents is None:
            self._contents, self._broken, self._partial = load_contents_by_key(self)

    def contents(self):
        """{key: content} of the artifacts whose content loads."""
        self._load()
        return self._contents

    def broken(self):
        """{key: [findings]} of the artifacts whose content does not load."""
        self._load()
        return self._broken

    def render_contents(self):
        """What Full Progress renders from: the loaded contents, and for an artifact that does not load, what could
        be read of it (its lede and decisions), so one broken feature does not stop the others being changed."""
        self._load()
        out = dict(self._partial)
        out.update(self._contents)
        return out

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


def load_contents_by_key(rec):
    """(contents, broken, partial): the content of each artifact that loads, the findings of each that does not,
    and what the renderer could read of those."""
    contents, broken, partial = {}, {}, {}
    for key, _kind, _e in rec.artifacts():
        if not isinstance(key, str) or not KEY_RE.match(key):
            continue
        try:
            contents[key] = _load_content(rec.dir, key)
        except R.ContentError as ce:
            broken[key] = problems_to_findings(getattr(ce, 'problems', None) or [str(ce)], key)
            if isinstance(getattr(ce, 'partial', None), dict):
                partial[key] = ce.partial
        except Exception as e:  # unreadable content of any kind
            broken[key] = [('R4.1', 'content/%s' % key, 'content cannot be read: %s' % e)]
    return contents, broken, partial


def load_contents(rec):
    contents, broken, _partial = load_contents_by_key(rec)
    return contents, [f for fs in broken.values() for f in fs]


def render_one(rec, key, stamp_t, stamp_i, links=None):
    """Render one artifact; `links` ({feature key: (href, path text)}) is only for the publish copy."""
    try:
        if key in rec.broken():
            raise Fail(1, 'content/%s is invalid; fix it with edit-content; nothing written' % key, rec.broken()[key])
        extra = {} if links is None else {'links': links}
        return R.render_artifact(rec.manifest, rec.registry, rec.render_contents(), key, PLUGIN_DIR,
                                 rec.dir, stamp_t, stamp_i, **extra)
    except Fail:
        raise
    except R.ContentError as ce:
        raise Fail(1, 'content is invalid; nothing written',
                   problems_to_findings(getattr(ce, 'problems', None) or [str(ce)], key))
    except Exception as e:
        raise Fail(2, 'render of %s failed: %s: %s' % (key, type(e).__name__, e))


# --------------------------------------------------------------------------
# validation (R7.1; the record-level checks of section 14)
# --------------------------------------------------------------------------


RETIRED_DIR = 'retired'      # docs/artifacts/retired/<key>.decisions.json: a retired feature's decisions (R4.32)


def retired_features(manifest):
    """The well-formed entries of the manifest's `retired_features` list (R4.31)."""
    v = manifest.get('retired_features') if isinstance(manifest, dict) else None
    return [e for e in v if isinstance(e, dict)] if isinstance(v, list) else []


def retired_entry(manifest, key):
    return next((e for e in retired_features(manifest) if e.get('key') == key), None)


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
    if m.get('merged_status') not in ('Live', 'Built'):
        f('R4.2', 'manifest.json', 'merged_status must be "Live" or "Built"')
    if m.get('design') not in ('default', 'design.css'):
        f('R4.2', 'manifest.json', 'design must be "default" or "design.css"')
    elif m.get('design') == 'design.css' and not (rec.dir / 'design.css').is_file():
        f('R5.10', 'manifest.json', 'design is "design.css" but design.css is missing from the record folder')
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
    for name, fields in (('retired', ('key', 'title', 'url', 'retired')), ('deleted', ('key', 'url', 'deleted'))):
        v = m.get(name)
        if v is None:
            continue
        if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
            f('R4.19', 'manifest.json', '%s must be a list of objects' % name)
            continue
        for x in v:
            for fld in fields:
                if not isinstance(x.get(fld), str):
                    f('R4.19', 'manifest.json', '%s: field "%s" is missing or not a string' % (name, fld))
            if isinstance(x.get('url'), str) and not re.match(r'^https?://\S+$', x['url']):
                f('R4.19', 'manifest.json', '%s: url is not an http(s) URL' % name)

    rf = m.get('retired_features')
    if rf is not None:
        if not isinstance(rf, list) or not all(isinstance(x, dict) for x in rf):
            f('R4.31', 'manifest.json', 'retired_features must be a list of objects')
            rf = []
        for x in rf:
            label = x.get('key') if isinstance(x.get('key'), str) else '?'
            for fld in ('key', 'title', 'prefix', 'retired', 'url', 'decisions'):
                if not isinstance(x.get(fld), str):
                    f('R4.31', 'manifest.json', 'retired_features %s: field "%s" is missing or not a string' % (label, fld))
            if isinstance(x.get('key'), str) and (not KEY_RE.match(x['key']) or x['key'] == FP_NAME):
                f('R4.31', 'manifest.json', 'retired_features: key %r is not a feature key' % x['key'])
            if isinstance(x.get('prefix'), str) and not PREFIX_RE.match(x['prefix']):
                f('R4.31', 'manifest.json', 'retired_features %s: prefix must be 2 to 5 capital letters' % label)
            if isinstance(x.get('retired'), str) and parse_iso(x['retired']) is None:
                f('R4.31', 'manifest.json', 'retired_features %s: retired is not an ISO time with offset' % label)
            if isinstance(x.get('url'), str) and x['url'] and not re.match(r'^https?://\S+$', x['url']):
                f('R4.31', 'manifest.json', 'retired_features %s: url is not an http(s) URL' % label)
            dec = x.get('decisions')
            if isinstance(dec, str) and dec and not (rec.dir / dec).is_file():
                f('R4.32', 'manifest.json', 'retired_features %s: the decisions archive %s is missing' % (label, dec))
    else:
        rf = []
    rf = [x for x in rf if isinstance(x, dict)]

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
        # only the full-progress entry is published, so only it has a url and a hash (R4.3)
        for fld in ('title', 'file') + (('url', 'published_sha256') if kind == 'full-progress' else ()):
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
        for fld in ('published_at',) if kind == 'full-progress' else ('updated',):    # R4.30
            v = e.get(fld)
            if v is not None and (not isinstance(v, str) or (v != '' and (
                    not R.ISO_OFFSET_RE.match(v) or parse_iso(v) is None))):
                f('R4.30', 'manifest.json', '%s: field "%s" must be an ISO time with an offset' % (label, fld))
        if kind == 'full-progress':
            pf = e.get('published_fingerprint')
            if pf is not None and not (isinstance(pf, str) and SHA_RE.match(pf)):
                f('R9.6', 'manifest.json', '%s: published_fingerprint is not a SHA-256' % label)
            du = e.get('deferred_until')
            if du is not None and (not isinstance(du, str) or parse_iso(du) is None):
                f('R9.7', 'manifest.json', '%s: deferred_until is not an ISO time with an offset' % label)
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
    live_keys = list(keys)
    for k in sorted({x.get('key') for x in rf if x.get('key') in keys}):
        f('R4.31', 'manifest.json', 'retired feature "%s" is also a live artifact key' % k)
    keys += [x.get('key') for x in rf]
    for k in sorted({x for x in keys if keys.count(x) > 1 and isinstance(x, str)}):
        f('R4.2', 'manifest.json', 'artifact key "%s" appears more than once' % k)
    prefixes = [e.get('prefix') for e in feats] + [x.get('prefix') for x in rf] + list(pp)
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
    feat_by_name.update({x.get('key'): x for x in rf if x.get('key') not in feat_by_name})    # R4.33: a retired key stays a valid owner
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
            f('R4.7', 'registry.json', '%s: status "%s" is not one of the nine statuses' % (label, st))
        if isinstance(t.get('changed'), str) and parse_iso(t['changed']) is None:
            f('R4.7', 'registry.json', '%s: changed is not an ISO time with offset' % label)
        if isinstance(t.get('item'), str) and len(t['item']) > 80:
            f('R4.8', 'registry.json', '%s: item is longer than 80 characters' % label)
        if isinstance(t.get('detail'), str) and len(t['detail']) > 600:
            f('R4.8', 'registry.json', '%s: detail is longer than 600 characters' % label)
        if 'expected_basis' in t:
            eb = t['expected_basis']
            if not isinstance(eb, str) or not eb.strip():
                f('R6.10', 'registry.json', '%s: expected_basis must be a non-empty string' % label)
            elif len(eb) > BASIS_MAX:
                f('R6.10', 'registry.json', '%s: expected_basis is longer than %d characters' % (label, BASIS_MAX))
            if isinstance(st, str) and st in statuses and st not in OPEN_STATUSES:
                f('R6.10', 'registry.json', '%s: expected_basis belongs on an open row, not on a %s row' % (label, st))
        if 'waits_on' in t:
            if t['waits_on'] not in WAITS_ON:
                f('R5.34a', 'registry.json', '%s: waits_on must be one of %s' % (label, ', '.join(WAITS_ON)))
            elif isinstance(st, str) and st in statuses and st not in ('Waiting', 'On hold'):
                f('R5.34a', 'registry.json', '%s: waits_on belongs on a Waiting or On hold row, not on a %s row' % (label, st))
        for req, msg in release_problems(t, {x.get('id'): x for x in tasks if isinstance(x, dict)}) + started_problems(t):
            f(req, 'registry.json', '%s: %s' % (label, msg))
        ex = t.get('expected')
        if isinstance(ex, str) and isinstance(st, str) and st in statuses:
            if st in ('Live', 'Built', 'Dropped'):
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
    task_ids = {t.get('id') for t in tasks if isinstance(t, dict)}
    for ckey, content in sorted(_c.items()):
        for d in content.get('decisions') or []:
            if d.get('task') and d['task'] not in task_ids:
                f('R5.18', 'content/%s' % ckey, '%s: task %s is not in the task registry' % (d.get('id'), d['task']))
    known = {k for k in live_keys if isinstance(k, str)}
    cdir = rec.dir / 'content'
    if cdir.is_dir():
        for p in sorted(cdir.iterdir()):
            if p.is_dir() and p.name not in known:
                f('R4.1', 'content/%s' % p.name, 'content folder has no artifact in the manifest')
    return sorted(set(F))


def check_html_findings(rec, key, html=None):
    e = rec.entry(key)
    if html is None:
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
    'complete': 'Built', 'completed': 'Built', 'finished': 'Built', 'closed': 'Built', 'resolved': 'Built',
    'built': 'Built', 'done': 'Built',
    'in progress': 'Running', 'started': 'Running', 'active': 'Running', 'working': 'Running',
    'wip': 'Running', 'ongoing': 'Running', 'open': 'Running', 'run': 'Running',
    'blocked': 'Needs you', 'review': 'Needs you', 'needs review': 'Needs you',
    'needs input': 'Needs you', 'awaiting you': 'Needs you', 'need you': 'Needs you', 'needs': 'Needs you',
    'pending': 'Waiting', 'ci': 'Waiting', 'queued': 'Waiting', 'wait': 'Waiting',
    'planned': 'To do', 'todo': 'To do', 'not started': 'To do', 'backlog': 'To do', 'new': 'To do',
    'draft': 'To do',
    'paused': 'On hold', 'hold': 'On hold', 'deferred': 'On hold', 'postponed': 'On hold',
    'parked': 'On hold', 'onhold': 'On hold',
    'dropped': 'Dropped', 'cancelled': 'Dropped', 'canceled': 'Dropped', 'abandoned': 'Dropped', 'folded': 'Dropped',
    'merged into': 'Dropped', 'obsolete': 'Dropped', 'superseded': 'Dropped',
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
    if str(word).strip().lower() == 'done':
        warn('status "Done" is deprecated and is stored as "Built" (finished, not yet released); '
             'use "Built", or "Live" once it is released')
        return 'Built'
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
        if e is fp:
            where = e.get('url') or '(not published)'
        else:
            where = 'a file in the repository, open it in a browser; never published'
        rows.append('| %s | `%s` | %s |' % (e.get('title', ''), e.get('file', ''), where))
    table = '\n'.join(['| Artifact | File | Where |', '|---|---|---|'] + rows)
    return (
        '# Project artifacts\n\n'
        'This folder is the record of %s\'s project artifacts (%s). It is generated and committed by\n'
        '`scripts/project_artifacts.py` of the `luismc-artifacts` plugin; do not edit the JSON or the\n'
        'rendered HTML by hand.\n\n'
        '%s\n\n'
        'A feature artifact is a standalone HTML file: open it in a browser, no server needed. It is\n'
        'never published. Only the full-progress artifact is a claude.ai artifact; it links to the\n'
        'feature files as local files.\n\n'
        '## Recreate the full-progress artifact if it was deleted on claude.ai\n\n'
        'The artifact is a disposable view; the record here is the source (R9.3).\n\n'
        '1. `python <plugin>/scripts/project_artifacts.py render` writes the HTML again from `content/`,\n'
        '   `registry.json` and `manifest.json`.\n'
        '2. `python <plugin>/scripts/project_artifacts.py pending` lists Full Progress when it must be\n'
        '   published and writes the publish copy (`.claude/artifacts-publish/`, not committed).\n'
        '3. Publish that file with the Artifact tool, once at the end of the turn, to the URL in\n'
        '   `manifest.json` when it still opens. When the publish is refused because the artifact no\n'
        '   longer exists, list your artifacts: if one has the same title, publish to that one; only if\n'
        '   none does, publish a new one. At most one artifact per title is ever created.\n'
        '4. `python <plugin>/scripts/project_artifacts.py mark-published full-progress --url URL` records\n'
        '   the URL and the hash of the committed render.\n\n'
        'Change a task only with `set-task-status`; edit prose only under `content/<key>/` and then run\n'
        '`edit-content <key>`.\n' % (manifest.get('project', 'the project'), SPEC, table))


def run_change(ctx, apply, new_ok=False):
    """lock -> migrate -> validate -> apply -> render -> validate -> write files in docs/artifacts/ and stop (R7.1).

    Nothing is committed or pushed; a failed change puts the files back as they were."""
    with locked(ctx):
        migrate_quietly(ctx)
        before = snapshot(ctx)
        if (ctx.record_dir / 'manifest.json').is_file():
            rec = Record.load(ctx.record_dir)
            mb = rec.manifest.get('default_branch')
            if isinstance(mb, str) and mb:
                ctx.branch = mb
            rec.pre_findings = all_findings(rec)           # earlier findings may stay; new ones may not (R7.1)
        else:
            if not new_ok:
                raise no_record_fail(ctx)
            rec = Record(ctx.record_dir, exists=False)
        try:
            result = apply(rec) or {}
            result = finish_change(ctx, rec, result)
            note = remove_stale_rule(ctx)
            if note:
                result.setdefault('notes', []).append(note)
        except BaseException as ex:
            restore(ctx, before)
            if rec.pre_findings and isinstance(ex, Exception) and not isinstance(ex, Fail):
                raise Fail(1, 'the record has earlier findings this change cannot work around (%s: %s); '
                              'nothing written' % (type(ex).__name__, ex), rec.pre_findings) from ex
            raise
        result['changed'] = snapshot(ctx) != before
        return result


def shipped_rule_copy(path):
    try:
        return AR is not None and path.is_file() and AR.is_shipped_rule(path.read_bytes())
    except OSError:
        return False


def remove_stale_rule(ctx):
    """R10.6: delete .claude/rules/project-artifacts.md from the working tree when its text is one a released
    plugin version shipped; an edited copy stays. The deletion is left uncommitted. Returns a note or None."""
    p = ctx.root / STALE_RULE_REL
    if not shipped_rule_copy(p):
        return None
    try:
        p.unlink()
    except OSError:
        return None
    return 'removed %s: an older copy of the plugin\'s rule, which the hooks now deliver' % STALE_RULE_REL


def finish_change(ctx, rec, result):
    """Write manifest/registry, render, README; validate the result (R7.1)."""
    if getattr(rec, 'noop', False) and not rec.retired_changed:
        result['rendered'] = []
        return add_notes(result, len(rec.pre_findings), rec.skipped)
    rec.sort_tasks()
    if rec.registry_changed() and rec.entry(FP_NAME) is not None:
        rec.render_keys.setdefault(FP_NAME, 'new')     # it embeds the registry (R5.9)
    if rec.migrated:
        rec.invalidate()
        for key, _kind, _e in rec.artifacts():
            if key in rec.broken():          # migrates when edit-content fixes it (R7.1a)
                rec.skipped.append(key)
            else:
                rec.render_keys.setdefault(key, 'new')
    else:
        refresh_stale(rec)
    if rec.entry(FP_NAME) is not None and any(
            v == 'new' and k != FP_NAME for k, v in rec.render_keys.items()):
        rec.render_keys.setdefault(FP_NAME, 'new')     # section 1 shows each feature's stamp (R5.6)
    rec.touch()
    now = rec.now()
    for key, how in rec.render_keys.items():           # the stamp Full Progress shows for a feature (R4.30)
        e = rec.entry(key)
        if how == 'new' and e is not None and rec.kind(key) == 'feature':
            e['updated'] = now.iso
    write_text(rec.dir / 'manifest.json', dump_json(rec.manifest))
    write_text(rec.dir / 'registry.json', dump_json(rec.registry))
    rec.invalidate()
    for key in sorted(rec.render_keys, key=lambda k: (k == FP_NAME, k)):    # Full Progress last (R7.5)
        stamp_t, stamp_i = now.text, now.iso
        if rec.render_keys[key] == 'keep':             # the page keeps its stamp (R5.38)
            kept = existing_stamp(read_html(rec.html_path(key)))
            if kept is not None:
                stamp_t, stamp_i = stamp_text_from_iso(kept), kept
        rec.write_html(key, render_one(rec, key, stamp_t, stamp_i))
    write_text(rec.dir / 'README.md', readme_text(rec.manifest))
    post = validate_structure(rec)
    for key in sorted(rec.rendered):
        post += check_html_findings(rec, key)
    # a file this change did not write has the findings it had before
    files = {e['file'] for _k, _kind, e in rec.artifacts() if isinstance(e.get('file'), str)}
    written = {rec.entry(k)['file'] for k in rec.rendered}
    post += [fd for fd in rec.pre_findings if fd[1] in files and fd[1] not in written]
    added, remaining = compare_findings(rec.pre_findings, post)
    if added:
        raise Fail(1, 'the change would make the record invalid; nothing written', added)
    result['rendered'] = sorted(rec.rendered)
    result['stamp'] = now.iso
    return add_notes(result, remaining, sorted(set(rec.skipped)))


def refresh_stale(rec):
    """R7.5: also render, with a new stamp, every artifact whose file differs from a fresh render with its own
    stamp: after a plugin upgrade changes the templates or the stylesheet, the next writing command brings every
    page up to date, not only the ones it changes. Compared before touch(), so a command that changes no task
    moves no stamp of an up-to-date page."""
    for key, _kind, e in rec.artifacts():
        if key in rec.render_keys or not isinstance(e.get('file'), str):
            continue
        if key in rec.broken():          # cannot be rendered until edit-content fixes it (R7.1a)
            continue
        old = read_html(rec.dir / e['file'])
        st = existing_stamp(old) if old is not None else None
        if st is None or render_one(rec, key, stamp_text_from_iso(st), st).replace('\r\n', '\n') != old:
            rec.render_keys[key] = 'new'


def all_findings(rec):
    """What a writing command compares before and after a change (R7.1): the record-level findings, those of
    every rendered file, and those a fresh render would show (a registry finding reappears in the file drawn from
    it, and is not an added one). An unreadable or unrenderable file is left to `check`."""
    out = validate_structure(rec)
    stamp = rec.now()
    for key, _kind, e in rec.artifacts():
        if not isinstance(key, str) or not KEY_RE.match(key) or not isinstance(e.get('file'), str):
            continue
        try:
            out += check_html_findings(rec, key)
            if key not in rec.broken():
                out += check_html_findings(rec, key, render_one(rec, key, stamp.text, stamp.iso))
        except Fail:
            pass
    return sorted(set(out))


def compare_findings(pre, post):
    """(added, remaining): the findings `post` has beyond `pre`, and how many of `pre` remain (R7.1).

    A finding is identified by its requirement and its file, never by its message, and counted: a second
    finding of the same kind in the same file is an added one."""
    def group(findings):
        out = {}
        for fd in sorted(set(findings)):
            out.setdefault((fd[0], fd[1]), []).append(fd)
        return out
    before, after = group(pre), group(post)
    added, remaining = [], 0
    for ident, fs in sorted(after.items()):
        old = before.get(ident, [])
        extra = len(fs) - len(old)
        remaining += min(len(fs), len(old))
        if extra > 0:
            old_msgs = {fd[2] for fd in old}
            new = [fd for fd in fs if fd[2] not in old_msgs]
            added += new if len(new) >= extra else fs[-extra:]
    return added, remaining


def add_notes(result, remaining, skipped):
    notes = []
    if remaining:
        notes.append('%d earlier finding%s remain%s; run check' % (remaining, '' if remaining == 1 else 's',
                                                                   's' if remaining == 1 else ''))
    if skipped:
        notes.append('not rendered, because its content is invalid: %s; edit-content renders it once fixed'
                     % ', '.join(skipped))
    if notes:
        result['notes'] = notes
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
        rec.message = ctx.rel + ': init'
        return {'command': 'init', 'project': project}

    res = run_change(ctx, apply, new_ok=True)
    changed, notes = install_session_files(ctx.root)
    res['session_changes'], res['notes'] = changed, notes
    emit(args, res, ['initialised the artifact record for %s (%s)' % (project, short(res))] +
         session_report(changed, notes) + ['record: %s' % ctx.record_dir])
    return 0


def short(res):
    return 'written to %s/' % current_rel() if res.get('changed') else 'unchanged'


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
        old = retired_entry(m, key)
        if old is not None:                      # R4.35: a retired key is reused only on purpose
            if not args.force:
                raise Fail(1, 'feature "%s" was retired on %s; its tasks (prefix %s) still belong to that key. '
                              'Use another key, or --force to bring the key back' % (key, old.get('retired', '')[:10], old.get('prefix')))
            m['retired_features'] = [x for x in m['retired_features'] if x is not old]
        taken = [e.get('prefix') for e in m['feature_artifacts']] + [x.get('prefix') for x in retired_features(m)] \
            + list(m['project_prefixes'])
        if prefix in taken:
            raise Fail(1, 'prefix %s is already registered' % prefix)
        title = 'Feature: %s' % name
        m['feature_artifacts'].append({      # never published: no url, no published_sha256 (R4.3)
            'key': key, 'title': title, 'file': R.artifact_file('feature', title),
            'prefix': prefix, 'apps': apps})
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
        rec.message = ctx.rel + ': add feature %s' % key
        return {'command': 'feature-new', 'key': key, 'title': title, 'prefix': prefix,
                'file': m['feature_artifacts'][-1]['file'], 'initialised': created}

    res = run_change(ctx, apply, new_ok=True)
    changed, notes = install_session_files(ctx.root)
    res['session_changes'], res['notes'] = changed, notes
    emit(args, res, ['added feature artifact "%s" (%s)' % (key, short(res)),
                     'to edit its prose: export-content %s --to DIR, edit, edit-content %s --from DIR' % (key, key)] +
         session_report(changed, notes))
    return 0


DROPPED_REASON_MAX = 80      # R5.49: longest `dropped_reason`
PHASE_NAMES = ('agents', 'join', 'ci', 'merge')       # R5.40
RISK_LABEL_MAX = 40
NO_RELEASE_MAX = 80          # R5.47a: longest `no_release` reason
_POINT_RE = re.compile(r'^\s*(?:(\d{1,2}) (' + '|'.join(MONTHS) + r') )?([01]?\d|2[0-3]):([0-5]\d)\s*$')


def _phase_point(text, now_dt, spec, flag='--phase'):
    m = _POINT_RE.match(text)
    if not m:
        raise Fail(1, '%s "%s": "%s" is not HH:MM or DD Mon HH:MM' % (flag, spec, text.strip()))
    day = int(m.group(1)) if m.group(1) else now_dt.day
    month = MONTHS.index(m.group(2)) + 1 if m.group(2) else now_dt.month
    try:
        return datetime(now_dt.year, month, day, int(m.group(3)), int(m.group(4)), tzinfo=now_dt.tzinfo)
    except ValueError:
        raise Fail(1, '%s "%s": %s %s is not a date' % (flag, spec, day, MONTHS[month - 1]))


def parse_phases(specs, now_dt):
    """R5.40: `--phase NAME=HH:MM-HH:MM` (today) or `NAME=DD Mon HH:MM-DD Mon HH:MM`, repeatable, in the project's
    zone; returns the stored list ordered by start, or [] for `--phase ""` (which clears them)."""
    if any(not str(s).strip() for s in specs):
        if len(specs) > 1:
            raise Fail(1, '--phase "" clears the phases; give it alone')
        return []
    out = []
    for spec in specs:
        name, sep, span = str(spec).partition('=')
        name = name.strip()
        if not sep or name not in PHASE_NAMES:
            raise Fail(1, '--phase "%s": use NAME=HH:MM-HH:MM with NAME one of %s' % (spec, ', '.join(PHASE_NAMES)))
        if any(p['name'] == name for p in out):
            raise Fail(1, '--phase: %s is given twice' % name)
        a, sep, b = span.partition('-')
        if not sep:
            raise Fail(1, '--phase "%s": use NAME=HH:MM-HH:MM' % spec)
        start, end = _phase_point(a, now_dt, spec), _phase_point(b, now_dt, spec)
        if end <= start:
            raise Fail(1, '--phase "%s": the end must be after the start' % spec)
        out.append({'name': name, 'start': start.isoformat(timespec='minutes'), 'end': end.isoformat(timespec='minutes')})
    return sorted(out, key=lambda p: (p['start'], p['name']))


def parse_started(text, now_dt):
    """R5.48: `--started "DD Mon ~HH:MM"` or `HH:MM` (today), in the project's zone, stored as ISO with the offset;
    `--started ""` clears it (returns None)."""
    text = str(text).strip()
    if not text:
        return None
    point = text.replace('~', '').strip()
    return _phase_point(point, now_dt, text, '--started').isoformat(timespec='minutes')


def started_problems(task):
    """R5.48: [(requirement, message)] for the `started` of one task row."""
    if 'started' not in task:
        return []
    st = parse_iso(task['started']) if isinstance(task['started'], str) else None
    if st is None:
        return [('R5.48', 'started must be an ISO time with offset')]
    exp = R._expected_datetime(str(task.get('expected', '')), st) if R is not None else None
    if task.get('status') in OPEN_STATUSES and exp is not None and st.replace(tzinfo=None) >= exp:
        return [('R5.48', 'started %s is not before Expected "%s"' % (task['started'], task.get('expected')))]
    return []


def apply_started(task, args, now_dt, prev=None):
    """R5.48: set or clear `started` from --started; a task that first moves to Running with none gets now."""
    given = getattr(args, 'started', None)
    if given is not None:
        started = parse_started(given, now_dt)
        if started:
            task['started'] = started
        else:
            task.pop('started', None)
    elif task.get('status') == 'Running' and prev != 'Running' and 'started' not in task:
        exp = R._expected_datetime(str(task.get('expected', '')), now_dt) if R is not None else None
        if exp is None or now_dt.replace(tzinfo=None) < exp:           # an overdue row has no honest start to record
            task['started'] = now_dt.isoformat(timespec='minutes')
    problems = started_problems(task)
    if problems:
        raise Fail(1, '%s: %s' % (task.get('id', 'new task'), '; '.join(m for _, m in problems)))


def parse_risk(text):
    """R5.40: `--risk "LABEL=MINUTES"` -> {"label", "minutes"}; "" clears it (returns None)."""
    text = str(text).strip()
    if not text:
        return None
    label, sep, minutes = text.rpartition('=')
    label = ' '.join(label.split())
    if not sep or not label or not minutes.strip().isdigit() or int(minutes) < 1:
        raise Fail(1, '--risk "%s": use "LABEL=MINUTES" with a whole number of minutes, for example "+1 fix round=10"' % text)
    if len(label) > RISK_LABEL_MAX:
        raise Fail(1, '--risk label is %d characters; at most %d' % (len(label), RISK_LABEL_MAX))
    return {'label': label, 'minutes': int(minutes)}


def dropped_problems(task, by_id):
    """R5.49: [(requirement, message)] for the dropped fields of one task row."""
    out = []
    into, reason = task.get('dropped_into'), task.get('dropped_reason')
    if task.get('status') != 'Dropped':
        if into is not None or reason is not None:
            out.append(('R5.49', 'dropped_into and dropped_reason belong to a Dropped row'))
        return out
    if reason is not None and (not isinstance(reason, str) or not reason.strip() or len(reason) > DROPPED_REASON_MAX):
        out.append(('R5.49', 'dropped_reason must be a non-empty text of at most %d characters' % DROPPED_REASON_MAX))
    if into is not None:
        target = by_id.get(into) if isinstance(into, str) else None
        if target is None or target is task:
            out.append(('R5.49', 'dropped_into names %r, which is not another task' % (into,)))
        elif is_release(task) and not is_release(target):
            out.append(('R5.49', 'a dropped release folds into another release; dropped_into names %s, which is not one' % into))
    elif reason is None:
        out.append(('R5.49', 'a Dropped row says why: dropped_into (the task that took the work) or dropped_reason'))
    elif is_release(task):
        out.append(('R5.49', 'a dropped release names the release that took its cargo: dropped_into'))
    return out


def release_problems(task, by_id):
    """R5.40, R5.41, R5.45, R5.47: [(requirement, message)] for the release fields of one task row."""
    out = []
    rel = task.get('release')
    phases, risk, rides = task.get('phases'), task.get('risk'), task.get('rides')
    if rel is True:
        out.append(('R5.45', 'release is still true; it needs a number (the next writing command numbers it)'))
    elif 'release' in task and release_number(task) is None:
        out.append(('R5.45', 'release must be a positive whole number (RELEASE-n)'))
    elif release_number(task) is not None and any(
            x is not task and release_number(x) == rel for x in by_id.values()):
        out.append(('R5.45', 'RELEASE-%d is used by more than one task' % rel))
    if (phases is not None or risk is not None) and not is_release(task):
        out.append(('R5.40', 'phases and risk belong to a release task (--release)'))
    if 'no_release' in task:                        # R5.47a: a task that ships nothing
        nr = task['no_release']
        if not isinstance(nr, str) or not nr.strip():
            out.append(('R5.47a', 'no_release must be a non-empty reason of at most %d characters' % NO_RELEASE_MAX))
        elif len(nr) > NO_RELEASE_MAX:
            out.append(('R5.47a', 'no_release is %d characters; at most %d' % (len(nr), NO_RELEASE_MAX)))
        if is_release(task) or rides:
            out.append(('R5.47a', 'a task that ships nothing is not a release and rides none (drop --no-release, or --release / --rides)'))
        if task.get('status') == 'Built':
            out.append(('R5.47a', 'a task that ships nothing is never Built; finished, it goes Live'))
    elif task.get('status') in ('Running', 'Built') and not is_release(task) and not rides:
        out.append(('R5.47', 'a %s task rides a release; give it --rides RELEASE-n (or the release task ID), '
                    'or --no-release REASON when it ships nothing' % task['status']))
    out.extend(dropped_problems(task, by_id))
    good = []
    if phases is not None:
        if not isinstance(phases, list) or not phases:
            out.append(('R5.40', 'phases must be a non-empty list'))
        else:
            seen = set()
            for p in phases:
                a = parse_iso(p.get('start')) if isinstance(p, dict) else None
                b = parse_iso(p.get('end')) if isinstance(p, dict) else None
                if not isinstance(p, dict) or p.get('name') not in PHASE_NAMES or a is None or b is None or b <= a:
                    out.append(('R5.40', 'a phase needs a name (%s) and a start before its end, ISO times with an offset'
                                % ', '.join(PHASE_NAMES)))
                elif p['name'] in seen:
                    out.append(('R5.40', 'phase %s appears twice' % p['name']))
                else:
                    seen.add(p['name'])
                    good.append(b)
    if risk is not None:
        if not (isinstance(risk, dict) and isinstance(risk.get('label'), str) and risk['label'].strip()
                and len(risk['label']) <= RISK_LABEL_MAX and isinstance(risk.get('minutes'), int)
                and not isinstance(risk['minutes'], bool) and risk['minutes'] >= 1):
            out.append(('R5.40', 'risk must be {"label": text of at most %d characters, "minutes": a whole number >= 1}' % RISK_LABEL_MAX))
    if rides is not None:
        target = by_id.get(rides) if isinstance(rides, str) else None
        if target is None:
            out.append(('R5.40', 'rides names %r, which is not a task' % (rides,)))
        elif target is task or not is_release(target):
            out.append(('R5.40', 'rides names %s, which is not a release task' % rides))
        elif target.get('status') == 'Dropped' and task.get('status') not in ('Live', 'Built', 'Dropped'):
            out.append(('R5.49', 'rides %s, a dropped release; move the task with --rides to the release that took the cargo' % rides))
    if good and task.get('status') in OPEN_STATUSES and isinstance(task.get('expected'), str):
        end = max(good)
        want = '%02d %s ~%02d:%02d' % (end.day, MONTHS[end.month - 1], end.hour, end.minute)
        have = task['expected'].split(';')[0].strip()
        if have != want:
            out.append(('R5.41', 'Expected is "%s" but the last phase ends at %s: a release\'s Expected is the end of its last '
                                 'phase (name a risk with --risk instead of padding)' % (have, want)))
    return out


def resolve_rides(text, by_id):
    """R5.45: `rides` stores a release's task ID; `RELEASE-<n>` names it by number."""
    m = re.match(r'^RELEASE-(\d+)$', text, re.I)
    if not m:
        return text
    for t in by_id.values():
        if release_number(t) == int(m.group(1)):
            return str(t.get('id'))
    raise Fail(1, '%s: no release has that number' % text)


def apply_dropped_fields(task, by_id, args):
    """R5.49: set the dropped fields from --into/--reason when the task is Dropped, remove them otherwise."""
    into, reason = getattr(args, 'into', None), getattr(args, 'reason', None)
    if task.get('status') != 'Dropped':
        if into is not None or reason is not None:
            raise Fail(1, '--into and --reason say why a task is Dropped; they go with the status Dropped')
        task.pop('dropped_into', None)
        task.pop('dropped_reason', None)
        return
    if into is not None:
        if into.strip():
            task['dropped_into'] = resolve_rides(into.strip(), by_id)
        else:
            task.pop('dropped_into', None)
    if reason is not None:
        reason = ' '.join(reason.split())
        if len(reason) > DROPPED_REASON_MAX:
            raise Fail(1, '--reason is %d characters; at most %d' % (len(reason), DROPPED_REASON_MAX))
        if reason:
            task['dropped_reason'] = reason
        else:
            task.pop('dropped_reason', None)


def apply_release_fields(task, by_id, args, now_dt):
    """Set or clear the release fields of `task` from --release/--phase/--risk/--rides; refuse a bad result."""
    no_release = getattr(args, 'no_release', None)
    if no_release is not None and no_release.strip():
        if getattr(args, 'release', False) or (args.rides is not None and args.rides.strip()):
            raise Fail(1, '--no-release says the task ships nothing; it cannot be given with --release or --rides')
        reason = ' '.join(no_release.split())
        if len(reason) > NO_RELEASE_MAX:
            raise Fail(1, '--no-release is %d characters; at most %d' % (len(reason), NO_RELEASE_MAX))
        task['no_release'] = reason
    elif no_release is not None:
        task.pop('no_release', None)
    if getattr(args, 'release', False) and release_number(task) is None:
        task['release'] = next_release_number(list(by_id.values()))       # R5.45: never reused
    if args.phase is not None:
        phases = parse_phases(args.phase, now_dt)
        if phases:
            task['phases'] = phases
        else:
            task.pop('phases', None)
    if args.risk is not None:
        risk = parse_risk(args.risk)
        if risk:
            task['risk'] = risk
        else:
            task.pop('risk', None)
    if args.rides is not None:
        if args.rides.strip():
            task['rides'] = resolve_rides(args.rides.strip(), by_id)
        else:
            task.pop('rides', None)
    apply_dropped_fields(task, by_id, args)
    problems = release_problems(task, by_id)
    if problems:
        raise Fail(1, '%s: %s' % (task.get('id', 'new task'), '; '.join(m for _, m in problems)))


def clean_basis(text):
    """R6.10: the basis as stored ('' clears it); refused when longer than BASIS_MAX."""
    text = ' '.join(str(text).split())
    if len(text) > BASIS_MAX:
        raise Fail(1, '--basis is %d characters; at most %d (what the estimate waits on, and how long)' % (len(text), BASIS_MAX))
    return text


def clean_waits_on(text):
    """R5.34a: `owner` or `work` ('' clears it); anything else is refused."""
    text = str(text).strip().lower()
    if text and text not in WAITS_ON:
        raise Fail(1, '--waits-on is %r; use owner (a task blocked on the owner), work (waiting on other work) or "" to clear' % text)
    return text


def cmd_task_add(args):
    ctx = make_ctx(args)
    status = require_status(args.status)
    waits_on = clean_waits_on(args.waits_on) if args.waits_on is not None else ''
    if waits_on and status not in ('Waiting', 'On hold'):
        warn('--waits-on ignored: only a Waiting or On hold row waits')
        waits_on = ''
    basis = clean_basis(args.basis) if args.basis is not None else ''
    if basis and status not in OPEN_STATUSES:
        warn('--basis ignored: a %s row has no estimate to base' % status)
        basis = ''

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
            if retired_entry(m, owner) is not None:
                raise Fail(1, 'feature "%s" is retired (R4.36); add the task to a live feature or the project' % owner)
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
        row = {'id': tid, 'owner': owner, 'app': app, 'status': status,
               'item': args.item, 'detail': args.detail, 'expected': args.expected,
               'changed': now.iso}
        if basis:
            row['expected_basis'] = basis
        if waits_on:
            row['waits_on'] = waits_on
        apply_release_fields(row, {t.get('id'): t for t in rec.tasks()}, args, now.dt)
        apply_started(row, args, now.dt)
        reg['tasks'].append(row)
        if owner != 'project':
            rec.render_keys[owner] = 'new'
        rec.render_keys[FP_NAME] = 'new'
        rec.message = ctx.rel + ': %s %s' % (tid, status)
        return {'command': 'task-add', 'id': tid, 'status': status}

    res = run_change(ctx, apply)
    emit(args, res, res['id'])
    if not args.json_out:
        print('project_artifacts: %s added (%s)' % (res['id'], short(res)), file=sys.stderr)
    return 0


ITEM_MAX = 80


def clean_item(text):
    """R4.8: the item as stored; refused when empty or longer than ITEM_MAX, as `check` reports it."""
    text = ' '.join(str(text).split())
    if not text:
        raise Fail(1, '--item is empty; give the task title')
    if len(text) > ITEM_MAX:
        raise Fail(1, '--item is %d characters; at most %d' % (len(text), ITEM_MAX))
    return text


def cmd_set_task_status(args):
    status = require_status(args.status)
    new_item = clean_item(args.item) if args.item is not None else None
    basis = clean_basis(args.basis) if args.basis is not None else None
    waits_on = clean_waits_on(args.waits_on) if args.waits_on is not None else None
    ctx = make_ctx(args)

    def apply(rec):
        task = next((t for t in rec.tasks() if t.get('id') == args.id), None)
        if task is None:
            raise Fail(1, 'unknown task ID "%s"' % args.id)
        if retired_entry(rec.manifest, task.get('owner')) is not None:
            raise Fail(1, '%s belongs to retired feature "%s" (R4.36); its tasks are history and do not change'
                       % (args.id, task.get('owner')))
        now = rec.now()
        prev = task['status']
        old_item = task['item']
        task['status'] = status
        task['changed'] = now.iso
        if new_item is not None:
            task['item'] = new_item
        if args.detail is not None:
            task['detail'] = args.detail
        if args.expected is not None:
            task['expected'] = args.expected
        elif status in ('Live', 'Built', 'Dropped'):
            task['expected'] = now.date          # R6.8
        if status not in OPEN_STATUSES:
            task.pop('expected_basis', None)     # R6.10: only an open row has an estimate to base
            if basis:
                warn('--basis ignored: a %s row has no estimate to base' % status)
        elif basis is not None:
            if basis:
                task['expected_basis'] = basis
            else:
                task.pop('expected_basis', None)
        if status not in ('Waiting', 'On hold'):
            task.pop('waits_on', None)           # R5.34a: only a waiting row waits on someone
            if waits_on:
                warn('--waits-on ignored: a %s row does not wait' % status)
        elif waits_on is not None:
            if waits_on:
                task['waits_on'] = waits_on
            else:
                task.pop('waits_on', None)
        apply_release_fields(task, {t.get('id'): t for t in rec.tasks()}, args, now.dt)
        apply_started(task, args, now.dt, prev)
        owner = task['owner']
        if owner != 'project':
            rec.render_keys[owner] = 'new'
            changes = []
            if new_item is not None and new_item != old_item:
                changes.append('%s item changed from "%s" to "%s"' % (args.id, old_item, new_item))
            if status == 'Dropped' and prev != 'Dropped':
                changes.append(R.dropped_line(task, {t.get('id'): t for t in rec.tasks()}))
            if args.history:
                changes.append(args.history)
            if changes:
                hp = rec.dir / 'content' / owner / 'history.json'
                try:
                    hist = json.loads(hp.read_text(encoding='utf-8')) if hp.is_file() else []
                except ValueError:
                    raise Fail(1, 'content/%s/history.json is not valid JSON' % owner)
                for change in reversed(changes):
                    hist.insert(0, {'date': now.text, 'change': change})
                write_text(hp, dump_json(hist))
                rec.invalidate()
        elif args.history or new_item is not None:
            warn('%s is a project task; project tasks have no History, nothing recorded there' % args.id)
        rec.render_keys[FP_NAME] = 'new'
        rec.message = ctx.rel + ': %s %s' % (args.id, status)
        return {'command': 'set-task-status', 'id': args.id, 'status': status, 'previous': prev,
                'expected': task['expected'], 'expected_basis': task.get('expected_basis', '')}

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
    """{name: bytes} of the regular files in a content folder, and of its assets/ folder as 'assets/<name>'
    (images of decision options, section 5.4); refuses anything else."""
    d = Path(d)
    if not d.is_dir():
        raise Fail(1, '%s is not a folder' % d)
    out = {}
    for p in sorted(d.iterdir()):
        if p.name == 'assets' and p.is_dir():
            for q in sorted(p.iterdir()):
                if not q.is_file():
                    raise Fail(1, '%s: assets/ holds files only, found %s' % (d, q.name))
                out['assets/' + q.name] = q.read_bytes()
            continue
        if not p.is_file():
            raise Fail(1, '%s: content folders hold files only (and assets/), found %s' % (d, p.name))
        out[p.name] = p.read_bytes()
    return out


def decisions_edit_problems(old, new):
    """R5.15: an edit never removes a decision and never changes the choice of a decided one."""
    try:
        before = json.loads(old.decode('utf-8-sig'))['decisions']
        before = [x for x in before if isinstance(x, dict)]
    except (ValueError, KeyError, TypeError, AttributeError):
        return []                     # nothing valid to hold the edit to
    try:
        after = {x.get('id'): x for x in json.loads(new.decode('utf-8-sig'))['decisions'] if isinstance(x, dict)}
    except (ValueError, KeyError, TypeError, AttributeError):
        after = {}
    problems = []
    for was in before:
        now = after.get(was.get('id'))
        if now is None:
            problems.append('%s was removed; decisions are never removed (a changed mind is a new decision with "replaces")'
                            % was.get('id'))
        elif was.get('status') == 'decided' and any(now.get(k) != was.get(k) for k in ('status', 'chosen', 'decided')):
            problems.append('%s is decided; its choice cannot change (a changed mind is a new decision with "replaces")'
                            % was.get('id'))
    return problems


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
        (dest / name).parent.mkdir(parents=True, exist_ok=True)
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
        new = {n: (b if n.startswith('assets/') else b.replace(b'\r\n', b'\n')) for n, b in src.items()}
        if d.is_dir() and new == content_files(d):
            rec.noop = True
            return {'command': 'edit-content', 'key': key, 'files': sorted(src), 'no_change': True}
        if (d / 'decisions.json').is_file():
            bad = decisions_edit_problems((d / 'decisions.json').read_bytes(), new.get('decisions.json', b''))
            if bad:
                raise Fail(1, 'content is invalid; nothing written',
                           [('R5.15', 'content/%s/decisions.json' % key, b) for b in bad])
        if d.exists():
            shutil.rmtree(str(d))
        d.mkdir(parents=True)
        for name, data in new.items():
            (d / name).parent.mkdir(parents=True, exist_ok=True)
            (d / name).write_bytes(data)
        rec.invalidate()
        if key in rec.broken():              # validates what the session supplied; other artifacts may stay as they are
            raise Fail(1, 'content is invalid; nothing written', rec.broken()[key])
        rec.render_keys[key] = 'new'
        if key != FP_NAME:
            rec.render_keys[FP_NAME] = 'new'   # section 1 quotes each lede
        rec.message = ctx.rel + ': edit %s' % key
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
        rec.message = ctx.rel + ': design %s' % ('default' if css is None else 'design.css')
        return {'command': 'design', 'design': rec.manifest['design']}

    res = run_change(ctx, apply)
    emit(args, res, 'design: %s (%s)' % (res['design'], short(res)))
    return 0


def cmd_render(args):
    ctx = make_ctx(args)

    def apply(rec):
        now = rec.now()
        for key, _kind, e in rec.artifacts():
            if key in rec.broken():          # cannot be rendered until edit-content fixes it (R7.1a)
                rec.skipped.append(key)
                continue
            old = read_html(rec.dir / e['file'])
            if args.all or old is None:
                rec.render_keys[key] = 'new'
                continue
            st = existing_stamp(old)
            if st is None or render_one(rec, key, stamp_text_from_iso(st), st).replace('\r\n', '\n') != old:
                rec.render_keys[key] = 'new'
        rec.message = ctx.rel + ': render'
        rec.noop = not rec.render_keys
        return {'command': 'render'}

    res = run_change(ctx, apply)
    emit(args, res, ['rendered: ' + (', '.join(res['rendered']) or 'nothing to do')])
    return 0


FINGERPRINT_TASK_FIELDS = ('id', 'owner', 'status', 'item', 'expected', 'release', 'rides', 'phases', 'risk', 'no_release',
                           'waits_on', 'started', 'dropped_into', 'dropped_reason')


def publish_fingerprint(rec):
    """R9.6: a hash of what the owner sees in Full Progress and can change: each task's id, owner, status, item,
    Expected and release fields, each open decision, and each feature row of section 1 (title and the note it
    quotes). A detail, a basis, a content section and the stamps are left out on purpose."""
    tasks = [[t.get(k) for k in FINGERPRINT_TASK_FIELDS] for t in rec.tasks() if isinstance(t, dict)]
    contents = rec.render_contents()
    open_of = getattr(R, 'open_decisions', None)
    features, decisions = [], []
    for key, kind, e in rec.artifacts():
        content = contents.get(key)
        if kind != 'feature' or not isinstance(content, dict):
            continue
        meta = content.get('meta') if isinstance(content.get('meta'), dict) else {}
        try:
            note = R._first_sentence(meta['lede']) if meta.get('lede') else ''
        except Exception:
            note = str(meta.get('lede', ''))
        features.append([key, e.get('title'), e.get('prefix'), note])
        for d in (open_of(content.get('decisions') or []) if open_of else []):
            decisions.append([key, d.get('id'), d.get('question'), d.get('task')])
    blob = json.dumps({'tasks': sorted(tasks, key=lambda x: str(x[0])), 'features': sorted(features, key=lambda x: str(x[0])),
                       'decisions': sorted(decisions, key=lambda x: (str(x[0]), str(x[1])))},
                      sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def deferral(rec, e):
    """R9.7: (until as a datetime, text 'HH:MM (label)') while the publish is deferred, else None."""
    until = parse_iso(e.get('deferred_until')) if isinstance(e.get('deferred_until'), str) else None
    if until is None or current_instant() >= until:
        return None
    zone = rec.manifest.get('timezone')
    local = _zoneinfo_now(until.astimezone(timezone.utc), zone) if zone else None
    local = local or until
    label = str(rec.manifest.get('timezone_label', '')).strip()
    return until, '%02d:%02d%s' % (local.hour, local.minute, ' (%s)' % label if label else '')


def cmd_mark_deferred(args):
    """R9.7: the daily publish limit was hit; Full Progress is not asked for again until the reset."""
    ctx = make_ctx(args)
    until = parse_iso(args.until)
    if until is None:
        raise Fail(1, '--until must be an ISO time with an offset, for example 2026-10-13T00:00:00+00:00')
    if until <= current_instant():
        raise Fail(1, '--until %s is not in the future' % args.until)

    def apply(rec):
        e = rec.entry(args.key)
        if e is None:
            raise Fail(1, 'unknown artifact key "%s"' % args.key)
        if rec.kind(args.key) != 'full-progress':
            raise Fail(1, '%s is a feature artifact: feature artifacts are never published; only the full-progress '
                          'artifact is (R9.5)' % args.key)
        e['deferred_until'] = until.isoformat(timespec='minutes')
        rec.message = ctx.rel + ': %s publish deferred' % args.key
        return {'command': 'mark-deferred', 'key': args.key, 'until': e['deferred_until']}

    res = run_change(ctx, apply)
    emit(args, res, 'recorded %s deferred until %s (%s)' % (args.key, res['until'], short(res)))
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
        if rec.kind(key) != 'full-progress':
            raise Fail(1, '%s is a feature artifact: feature artifacts are standalone files in the repository (%s) '
                          'and are never published; only the full-progress artifact is (R9.5)' % (key, e.get('file', '')))
        old = read_html(rec.dir / e['file'])
        st = existing_stamp(old)
        if old is None or st is None:
            raise Fail(1, '%s has not been rendered; run render first' % e['file'])
        if render_one(rec, key, stamp_text_from_iso(st), st).replace('\r\n', '\n') != old:
            raise Fail(1, '%s differs from a fresh render; run render first' % e['file'])
        stale = stale_copy_reason(ctx, rec, e)
        if stale:
            raise Fail(1, 'refusing to mark published: ' + stale)
        e['url'] = url
        # the hash of the committed render, not of the publish copy (R5.32): nothing links to the url,
        # so no other artifact changes
        e['published_sha256'] = sha_of_file(rec.html_path(key))
        e['published_at'] = rec.now().iso
        e['published_fingerprint'] = publish_fingerprint(rec)       # R9.6
        e.pop('deferred_until', None)                                # R9.7: a publish ends any deferral
        # each feature page says when Full Progress was published (R5.38), without a new stamp: a new stamp
        # would change Full Progress's section 1, which would need publishing again, and so on
        for fkey, _k, fe in rec.artifacts():
            if fkey == key or fkey in rec.broken() or not isinstance(fe.get('file'), str):
                continue
            fold = read_html(rec.dir / fe['file'])
            fst = existing_stamp(fold)
            if fst is not None and render_one(rec, fkey, stamp_text_from_iso(fst), fst).replace('\r\n', '\n') != fold:
                rec.render_keys[fkey] = 'keep'
        rec.message = ctx.rel + ': published %s' % key
        return {'command': 'mark-published', 'key': key, 'url': url, 'sha256': e['published_sha256']}

    res = run_change(ctx, apply)
    emit(args, res, 'recorded %s -> %s (%s)' % (key, url, short(res)))
    return 0


def cmd_mark_deleted(args):
    """R4.21: the owner confirmed and the session deleted the page (or it is gone): it leaves the retired list."""
    ctx = make_ctx(args)
    url = args.url
    if not re.match(r'^https?://\S+$', url):
        raise Fail(1, 'url must be an http(s) URL')
    if AR is None:
        raise Fail(2, 'artifact_retire.py cannot be imported: %s' % _RETIRE_ERROR)

    def apply(rec):
        fp = rec.manifest.get('full_progress_artifact')
        if isinstance(fp, dict) and fp.get('url') == url:
            raise Fail(1, 'that is the Full Progress URL: Full Progress is published, not retired')
        try:
            entry = AR.mark_deleted(rec.manifest, url, args.key, rec.now().iso, args.gone)
        except ValueError as ex:
            raise Fail(1, str(ex))
        rec.message = ctx.rel + ': deleted the old page of %s' % (entry['key'] or url)
        return {'command': 'mark-deleted', 'key': entry['key'], 'url': url, 'gone': bool(args.gone)}

    res = run_change(ctx, apply)
    emit(args, res, 'recorded %s deleted (%s)' % (url, short(res)))
    return 0


RETIRABLE_STATUSES = ('Live', 'Dropped')     # R4.33: a finished feature has only these


def _size_text(n):
    return '%.1f MB' % (n / 1048576.0) if n >= 1048576 else '%.1f KB' % (n / 1024.0)


def retire_plan(rec, key):
    """R4.33: what retiring `key` removes and keeps; a Fail when the feature is not finished."""
    if retired_entry(rec.manifest, key) is not None:
        raise Fail(1, 'feature "%s" is already retired' % key)
    entry = rec.entry(key) if rec.kind(key) == 'feature' else None
    if entry is None:
        raise Fail(1, 'unknown feature "%s"' % key)
    tasks = [t for t in rec.tasks() if t.get('owner') == key]
    unfinished = [t for t in tasks if t.get('status') not in RETIRABLE_STATUSES]
    if unfinished:
        raise Fail(1, 'feature "%s" is not finished; refused: %s (every task must be %s)' % (
            key, ', '.join('%s %s' % (t.get('id'), t.get('status')) for t in unfinished), ' or '.join(RETIRABLE_STATUSES)))
    if key in rec.broken():
        raise Fail(1, 'content/%s is invalid; fix it with edit-content before retiring it' % key, rec.broken()[key])
    open_dec = R.open_decisions(rec.contents()[key].get('decisions') or [])
    if open_dec:
        raise Fail(1, 'feature "%s" has open decisions (%s); decide them first' % (
            key, ', '.join(str(d.get('id')) for d in open_dec)))
    files = []
    page = rec.dir / entry['file']
    if page.is_file():
        files.append((entry['file'], page.stat().st_size))
    cdir = rec.dir / 'content' / key
    if cdir.is_dir():
        files += [(p.relative_to(rec.dir).as_posix(), p.stat().st_size) for p in sorted(cdir.rglob('*')) if p.is_file()]
    src = cdir / 'decisions.json'
    archive = ''
    if src.is_file():
        archive = '%s/%s.decisions.json' % (RETIRED_DIR, key)
        n = 2
        while (rec.dir / archive).is_file():            # a reused key retired again keeps the earlier archive
            archive = '%s/%s.decisions-%d.json' % (RETIRED_DIR, key, n)
            n += 1
    url = entry.get('url') or ''
    if not url:
        for name in ('retired', 'deleted'):
            url = url or next((x.get('url', '') for x in (rec.manifest.get(name) or [])
                               if isinstance(x, dict) and x.get('key') == key), '')
    return {'entry': entry, 'tasks': tasks, 'files': files, 'bytes': sum(n for _f, n in files),
            'archive': archive, 'archive_bytes': src.stat().st_size if archive else 0, 'url': url}


def cmd_retire(args):
    """R4.31 to R4.36: move a finished feature to `retired_features`, keep its decisions, delete its files."""
    key = args.key
    if not KEY_RE.match(key) or key == FP_NAME:
        raise Fail(1, 'key must be a feature key')
    summary = {}

    def apply(rec):
        plan = retire_plan(rec, key)
        entry = plan['entry']
        if not args.yes:
            summary.update(plan)
            rec.noop = True                      # a dry run writes nothing
            return {'command': 'retire', 'dry_run': True}
        m = rec.manifest
        m['feature_artifacts'] = [e for e in m['feature_artifacts'] if e.get('key') != key]
        m.setdefault('retired_features', []).append({
            'key': key, 'title': entry['title'], 'prefix': entry['prefix'], 'retired': rec.now().iso,
            'url': plan['url'], 'decisions': plan['archive']})
        if plan['archive']:
            dest = rec.dir / plan['archive']
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((rec.dir / 'content' / key / 'decisions.json').read_bytes())
        page = rec.dir / entry['file']
        if page.is_file():
            page.unlink()
        shutil.rmtree(str(rec.dir / 'content' / key), ignore_errors=True)
        rec.invalidate()
        rec.render_keys[FP_NAME] = 'new'
        rec.message = ctx.rel + ': retire feature %s' % key
        summary.update(plan)
        return {'command': 'retire', 'dry_run': False, 'key': key}

    ctx = make_ctx(args)
    if args.yes:
        res = run_change(ctx, apply)
    else:
        _ctx, rec = load_for_read(args)
        rec.pre_findings = []
        res = apply(rec)
    plan = summary
    res.update({'key': key, 'files': [{'path': f, 'bytes': n} for f, n in plan['files']], 'bytes': plan['bytes'],
                'tasks': [t['id'] for t in plan['tasks']], 'archive': plan['archive'],
                'archive_bytes': plan['archive_bytes'], 'url': plan['url']})
    verb = 'deleted' if args.yes else 'would delete'
    lines = ['retire %s: %s' % (key, 'done' if args.yes else 'dry run, nothing changed; add --yes to retire')]
    lines.append('  tasks kept (owner stays "%s"): %s' % (key, ', '.join(res['tasks']) or 'none'))
    for f, n in plan['files']:
        lines.append('  %s %s (%s)' % (verb, f, _size_text(n)))
    lines.append('  %s: %d files, %s' % (verb, len(plan['files']), _size_text(plan['bytes'])))
    if plan['archive']:
        lines.append('  %s %s (%s)' % ('wrote' if args.yes else 'would write', plan['archive'], _size_text(plan['archive_bytes'])))
    lines.append('  the claude.ai page, if any, is never deleted here (R4.23)')
    emit(args, res, lines)
    return 0



def cmd_commit(args):
    """Removed in 1.8.0 (R4.28): the plugin never commits or pushes."""
    raise Fail(1, NO_COMMIT_MSG % current_rel())


cmd_push = cmd_commit


def cmd_migrate(args):
    """Copy the old record worktree's docs/artifacts/ into the working tree when newer (R4.24); idempotent."""
    ctx = make_ctx(args)
    with locked(ctx):
        note = migrate_record(ctx)
    if note:
        print(note)
    return 0


def load_for_read(args):
    """Return (ctx, Record) for a read-only command, from docs/artifacts/ of the working tree."""
    ctx = make_ctx(args)
    with locked(ctx):
        migrate_quietly(ctx)
    if not (ctx.record_dir / 'manifest.json').is_file():
        raise no_record_fail(ctx)
    return ctx, Record.load(ctx.record_dir)


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


def done_notes(rec):
    """A note (never a finding) for the retired status Done, read as Built (R6.9)."""
    out = []
    if rec.old_done:
        out.append('registry.json: %s still use the retired status Done; they are read as Built and the next '
                   'writing command rewrites them' % ', '.join(sorted(rec.old_done)))
    if rec.old_merged and not rec.old_done:
        out.append('manifest.json: merged_status Done is read as Built; the next writing command rewrites it')
    return out


def release_notes(rec):
    """A note (never a finding) for older rows that say `"release": true`, numbered when the record loads (R5.45)."""
    if not rec.old_releases:
        return []
    by_id = {t.get('id'): t for t in rec.tasks()}
    return ['registry.json: %s say "release": true; they are read as %s and the next writing command numbers them'
            % (', '.join(sorted(rec.old_releases)), ', '.join('RELEASE-%s' % by_id[i].get('release') for i in sorted(rec.old_releases)))]


def feature_url_notes(rec):
    """A note (never a finding) for an older manifest whose feature entries hold a url (R4.18)."""
    if not rec.old_urls:
        return []
    return ['manifest.json: feature artifact(s) %s hold a url or published_sha256; feature artifacts are no longer '
            'published, so the next writing command moves each url to the retired list and renders every artifact '
            'again' % ', '.join(sorted(rec.old_urls))]


def retired_notes(rec):
    """A note (never a finding) listing the old claude.ai pages still to delete (R4.22)."""
    entries = AR.retired_pages(rec.manifest) if AR else []
    if not entries:
        return []
    return ['claude.ai pages of feature artifacts are still up: %s; ask the owner to confirm, delete each confirmed '
            'one with the Artifact tool (action: delete), then run mark-deleted'
            % '; '.join('%s %s' % (e.get('key'), e.get('url')) for e in entries)]


def cmd_check(args):
    if R is None:
        raise Fail(2, 'render_artifacts.py cannot be imported: %s' % _RENDER_ERROR)
    if args.record:
        d = Path(args.record)
        rel = current_rel(d) if (d / '.claude' / 'artifacts.json').is_file() else RECORD_REL
        if (d / rel / 'manifest.json').is_file():
            d = d / rel
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
    notes = setting_ignored_notes(session_root() or '.') + rule_copy_notes() + done_notes(rec) + release_notes(rec) + feature_url_notes(rec) + retired_notes(rec)
    warnings = decision_warnings(rec) + lede_warnings(rec) + overdue_warnings(rec)
    if getattr(args, 'json_out', False):
        result = {'findings': [{'req': r, 'file': f, 'message': m} for r, f, m in findings],
                  'notes': notes}
        if warnings:
            result['warnings'] = [{'file': f, 'message': m} for f, m in warnings]
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print('\n'.join(fmt_finding(x) for x in findings) if findings else 'record is clean')
        for n in notes:
            print('note: ' + n)
        for f, m in warnings:
            print('warning  %s: %s' % (f, m))
    return 1 if findings else 0


def overdue_warnings(rec):
    """R6.14 (DL-63): an open row whose Expected time is in the past. [(file, message)]"""
    if H is None:
        return []
    return [('registry.json', '%s: set a new Expected (set-task-status %s <status> --expected ...) or the real status'
             % (H.overdue_text(t), t.get('id'))) for t, _when in H.overdue_tasks(rec.tasks(), rec.manifest)]


def lede_warnings(rec):
    """R5.37: a lede over 300 characters, per artifact's meta.json. [(file, message)]"""
    warn_of = getattr(R, 'lede_warnings', None)
    if warn_of is None:
        return []
    contents, _findings = load_contents(rec)
    return [('content/%s/meta.json' % key, m) for key, content in sorted(contents.items()) for m in warn_of(content)]


def decision_warnings(rec):
    """Section 5.4 (R5.26): an open decision with no task in Needs you in its feature. [(file, message)]"""
    open_of = getattr(R, 'open_decisions', None)
    if open_of is None:
        return []
    contents, _findings = load_contents(rec)
    by_id = {t.get('id'): t for t in rec.tasks() if isinstance(t, dict)}
    out = []
    for key, content in sorted(contents.items()):
        needs = [t for t in by_id.values() if t.get('owner') == key and t.get('status') == 'Needs you']
        for d in open_of(content.get('decisions') or []):
            tid = d.get('task')
            if tid:
                t = by_id.get(tid)
                if t is None or t.get('owner') != key or t.get('status') != 'Needs you':
                    out.append(('content/%s' % key, '%s is open, but its task %s is not in Needs you in this feature; '
                                'set it to Needs you' % (d['id'], tid)))
            elif not needs:
                out.append(('content/%s' % key, '%s is open, but no task in this feature is in Needs you; add one or set '
                            'the decision\'s "task"' % d['id']))
    return out


def feature_link_map(root, rec):
    """R5.31: {feature key: (file:/// URL, path as text)} for the publish copy. The target is the feature
    file in docs/artifacts/ of the working tree. The URL is the absolute path with forward slashes,
    percent-encoded by pathlib (a space is %20)."""
    out = {}
    for key, kind, e in rec.artifacts():
        if kind != 'feature' or not isinstance(e.get('file'), str):
            continue
        target = rec.dir / e['file']
        absolute = Path(os.path.abspath(str(target)))
        out[key] = (absolute.as_uri(), absolute.as_posix())
    return out


COPY_META_SUFFIX = '.meta.json'


def copy_meta_path(dest):
    return Path(str(dest) + COPY_META_SUFFIX)


def write_copy_meta(dest, rec_dir):
    """R9.11: the hash and write time of a publish copy, beside it, so mark-published can tell a stale copy."""
    meta = {'sha256': hashlib.sha256(Path(dest).read_bytes()).hexdigest(),
            'written_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'inputs_sha256': record_inputs_hash(rec_dir)}
    write_text(copy_meta_path(dest), json.dumps(meta))
    return meta


def read_copy_meta(dest):
    try:
        meta = json.loads(copy_meta_path(dest).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def record_inputs_hash(rec_dir):
    """Hash of the files Full Progress is made from: the registry, the content, the design and the rendered pages.
    The manifest and the README are left out: mark-deferred and mark-published write them without changing what
    the owner sees. Content, not modification times, so a rewrite with the same bytes is no change."""
    h = hashlib.sha256()
    for d, dirs, files in os.walk(str(rec_dir)):
        dirs.sort()
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(d, name), str(rec_dir)).replace(os.sep, '/')
            if not (rel in ('registry.json', 'design.css') or rel.startswith('content/') or rel.endswith('.html')):
                continue
            try:
                data = Path(d, name).read_bytes()
            except OSError:
                continue
            h.update(rel.encode('utf-8') + b'\0' + hashlib.sha256(data).digest())
    return h.hexdigest()


def stale_copy_reason(ctx, rec, e):
    """R9.11 (DL-62): why the publish copy of Full Progress must not be marked published, or None. A copy that was
    never written has nothing to go stale (the committed file is published as it is)."""
    dest = ctx.root / PUBLISH_REL / str(e.get('file', ''))
    if not dest.is_file():
        return None
    meta = read_copy_meta(dest)
    if meta is None:
        return None
    if hashlib.sha256(dest.read_bytes()).hexdigest() != meta.get('sha256'):
        return '%s was edited after pending wrote it; run pending --json and publish that copy unedited' % dest
    if meta.get('inputs_sha256') != record_inputs_hash(rec.dir):
        return ('the record changed after the publish copy %s was written (the copy is older than the latest record '
                'change); run pending --json, publish the fresh copy, then mark-published' % dest)
    return None


def write_publish_copy(ctx, rec, key, e):
    """R5.31: render Full Progress, from the committed render's stamp, with absolute links to the feature
    files, to .claude/artifacts-publish/<file> (git-ignored). Returns its path, or None when it cannot be made."""
    old = read_html(rec.dir / e['file'])
    st = existing_stamp(old)
    if st is None:
        return None
    try:
        html = render_one(rec, key, stamp_text_from_iso(st), st, links=feature_link_map(ctx.root, rec))
    except Fail as fl:
        warn('the publish copy of %s was not written (%s); publish the committed file as it is' % (key, fl.msg))
        return None
    dest = ctx.root / PUBLISH_REL / e['file']
    write_text(dest, html)
    write_copy_meta(dest, rec.dir)
    if (git_out(ctx.root, 'status', '--porcelain', '--ignored', '--untracked-files=all', '--', str(dest)) or '').startswith('??'):
        warn('.gitignore does not ignore %s/ (the publish copy); add that line' % PUBLISH_REL.replace(os.sep, '/'))
    return str(dest)


def cmd_pending(args):
    """Lists Full Progress when its committed render changed since the last publish, and queued events.
    A feature artifact is never listed (R9.5)."""
    ctx, rec = load_for_read(args)
    refresh = bool(getattr(args, 'refresh', False))
    arts, deferred = [], []
    if rec is not None:
        for key, kind, e in rec.artifacts():
            if kind != 'full-progress':
                continue
            p = rec.dir / str(e.get('file', ''))
            copy_path = None
            if not p.is_file():
                reason = 'not rendered yet; run render'
            else:
                h = sha_of_file(p)
                if not e.get('published_sha256') and not e.get('url'):
                    reason = 'never published'
                elif e.get('url') and not e.get('published_sha256'):
                    reason = 'adopted, not yet published from the record'
                elif h != e.get('published_sha256'):
                    # R9.6: a render that differs only in a detail, a basis, a content section or the stamp is no
                    # reason to publish; a record with no stored fingerprint needs one publish
                    if e.get('published_fingerprint') == publish_fingerprint(rec) and not refresh:
                        continue
                    reason = 'changed since last publish'
                elif refresh:
                    reason = 'refresh requested (hourly or release change)'
                else:
                    continue
                wait = deferral(rec, e)
                if wait is not None:          # R9.7: listed, not asked for, until the reset
                    deferred.append({'key': key, 'kind': kind, 'title': e.get('title', ''), 'file': e.get('file', ''),
                                     'until': wait[0].isoformat(timespec='minutes'),
                                     'reason': 'deferred until %s' % wait[1]})
                    continue
                copy_path = write_publish_copy(ctx, rec, key, e)
            item = {'key': key, 'kind': kind, 'title': e.get('title', ''), 'file': e.get('file', ''),
                    'path': copy_path or str(p), 'url': e.get('url', ''), 'reason': reason}
            meta = read_copy_meta(copy_path) if copy_path else None
            if meta:          # R9.11: what mark-published will compare the copy against
                item['copy_sha256'] = meta.get('sha256')
                item['copy_written_at'] = meta.get('written_at')
            arts.append(item)
    queue = artifact_queue.read_queue(str(ctx.root))
    retired = [{'key': e.get('key', ''), 'title': e.get('title', ''), 'url': e.get('url', ''),
                'retired': e.get('retired', '')} for e in (AR.retired_pages(rec.manifest) if AR and rec else [])]
    if args.json_out:
        out = {'artifacts': arts, 'queue': queue, 'retired': retired}
        if deferred:
            out['deferred'] = deferred
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for a in arts:
            print('publish %s (%s): %s%s' % (a['key'], a['path'], a['reason'],
                                             '' if a['url'] else ' [no URL yet]'))
        for ev in queue:
            print('queued %s -> %s (%s)' % (ev.get('id'), ev.get('suggested_status'), ev.get('event')))
        for d in deferred:
            print('deferred %s (%s): %s' % (d['key'], d['file'], d['reason']))
        if not arts and not queue and not deferred:
            print('nothing pending')
        for e in retired:
            print('retired %s "%s" %s: ask the owner to confirm, delete it with the Artifact tool (action: delete), '
                  'then run mark-deleted %s --url %s' % (e['key'], e['title'], e['url'], e['key'], e['url']))
    return 1 if (arts or queue) else 0     # retired pages never change the exit code (R4.22)


def cmd_worktree(args):
    """Prints the record directory, <root>/docs/artifacts: the record worktree is retired (R4.24)."""
    if artifact_queue is None:
        raise Fail(2, 'artifact_queue.py cannot be imported: %s' % _QUEUE_ERROR)
    root = session_root()
    if not root:
        raise Fail(2, 'not inside a git repository')
    path = str(Path(root) / record_rel_or_fail(root))
    emit(args, {'worktree': path}, path)
    return 0


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


def cmd_promote_to_spec(args):
    """DOCSPEC R4.10, R10.4: write a feature artifact's decided content to docs/features/<feature>/spec.md
    (luismc-docs template). Dry run without --apply (diff when the spec exists); merges section by section, never deletes spec text; touches nothing in the record."""
    if PROMOTE is None:
        raise Fail(2, 'artifact_promote.py cannot be imported: %s' % _PROMOTE_ERROR)
    key = args.key
    if not KEY_RE.match(key) or key == FP_NAME:
        raise Fail(1, 'key must be a feature artifact key (lowercase letters, digits and hyphens)')
    fid = args.feature or key
    if not KEY_RE.match(fid):
        raise Fail(1, '--feature must be lowercase letters, digits and hyphens (the folder name, DOCSPEC R4.1)')
    ctx, rec = load_for_read(args)
    entry = rec.entry(key)
    if entry is None:
        raise Fail(1, 'unknown artifact key "%s"' % key)
    src = rec.dir / 'content' / key
    if not src.is_dir():
        raise Fail(2, 'content/%s is missing from the record' % key)
    files = content_files(src)
    meta = json.loads(files['meta.json'].decode('utf-8')) if 'meta.json' in files else {}
    title = entry.get('title', key)
    title = title[len('Feature: '):] if title.startswith('Feature: ') else title
    secs = PROMOTE.sections(files)
    decs, open_decs = PROMOTE.decided(files)
    dest = ctx.root / 'docs' / 'features' / fid / 'spec.md'
    rel = dest.relative_to(ctx.root).as_posix()
    apply = args.yes or args.apply
    cfg = {}
    try:
        cfg = json.loads((ctx.root / 'docs' / 'docs.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    topics = PROMOTE.topics_from(meta.get('lede', ''), secs, meta.get('topics'), cfg.get('topics') or [])
    apps = entry.get('apps') or []
    _, unmapped = PROMOTE.slots_for(meta.get('lede', ''), secs, decs)
    result = {'command': 'promote-to-spec', 'key': key, 'spec': rel, 'sections': [t for t, _ in secs],
              'mapping': {t: PROMOTE.classify(t) for t, _ in secs}, 'unmapped': unmapped, 'topics': topics,
              'decisions_promoted': [d.get('id') for d in decs], 'decisions_open': [d.get('id') for d in open_decs],
              'written': False, 'dry_run': not apply, 'merge': dest.exists()}
    notes = []
    if open_decs:
        notes.append('open decisions are not promoted: %s' % ', '.join(result['decisions_open']))
    if unmapped:
        notes.append('no template section matched these headings, so they sit under 3 How it works: %s' % ', '.join(unmapped))
    if dest.exists():
        old = dest.read_text(encoding='utf-8')
        text, changes = PROMOTE.merge_spec(old, fid, title, apps, entry.get('file', ''), meta.get('lede', ''), secs, decs, topics)
        text = text if text.endswith('\n') else text + '\n'
        result['changes'] = changes
        result['diff'] = PROMOTE.diff(old, text, rel)
        removed = [l for l in result['diff'].splitlines() if l.startswith('-') and not l.startswith('---')]
        result['removed_lines'] = len(removed)   # the merge appends and fills; a removal is a placeholder or a front matter blank
        what = 'merge into the existing %s (%d change(s))' % (rel, len(changes))
    else:
        text = PROMOTE.build_spec(fid, title, apps, entry.get('file', ''), meta.get('lede', ''), secs, decs, topics)
        changes, what = [], 'write %s from %d section(s) and %d decided decision(s)' % (rel, len(secs), len(decs))
        result['changes'] = []
    if apply:
        if dest.exists() and text == old:
            human = ['%s already holds everything the page says; nothing changed' % rel] + ['  ' + c for c in changes]
        else:
            write_text(dest, text if text.endswith('\n') else text + '\n')
            result['written'] = True
            human = ['%s %s' % ('merged into' if result['merge'] else 'wrote', rel)] + ['  ' + c for c in changes] + \
                    ['review it against the feature-spec template, then commit it; the artifact stays as it is (nothing in the record changed)']
    else:
        human = ['dry run (nothing written); with --apply this would %s' % what] + ['  ' + c for c in changes]
        if result.get('diff'):
            human += ['', result['diff'].rstrip()]
    result['notes'] = notes
    emit(args, result, human)
    return 0


def cmd_move_record(args):
    """Move the record folder to another folder under docs/ and write the record_dir setting (a plain file
    move, no git). Without --yes it only says what it would do."""
    if artifact_queue is None:
        raise Fail(2, 'artifact_queue.py cannot be imported: %s' % _QUEUE_ERROR)
    root = session_root()
    if not root:
        raise Fail(2, 'not inside a git repository')
    root = Path(root)
    old_rel = record_rel_or_fail(root)
    try:
        new_rel = artifact_queue.check_record_rel(args.new_dir, 'the new record folder')
    except artifact_queue.RecordDirError as e:
        raise Fail(2, str(e))
    old_dir, new_dir = root / old_rel, root / new_rel
    if new_rel == old_rel:
        emit(args, {'moved': False, 'from': old_rel, 'to': new_rel}, 'the record is already in %s/; nothing to do' % old_rel)
        return 0
    if new_rel.startswith(old_rel + '/') or old_rel.startswith(new_rel + '/'):
        raise Fail(2, 'the new folder %s and the current one %s must not contain each other' % (new_rel, old_rel))
    has_old = old_dir.is_dir()
    if new_dir.exists() and (not new_dir.is_dir() or any(new_dir.iterdir())):
        raise Fail(1, '%s exists and is not an empty folder; move or remove it first' % new_rel)
    settings = root / artifact_queue.SETTINGS_NAME
    steps = ['move %s/ to %s/' % (old_rel, new_rel) if has_old else 'no record folder at %s/ to move' % old_rel,
             '%s record_dir = %s' % (artifact_queue.SETTINGS_NAME.replace(os.sep, '/'), new_rel)
             if new_rel != artifact_queue.DEFAULT_RECORD_REL else
             'remove record_dir from %s (back to the default)' % artifact_queue.SETTINGS_NAME.replace(os.sep, '/')]
    result = {'moved': False, 'from': old_rel, 'to': new_rel, 'dry_run': not args.yes, 'steps': steps}
    if not args.yes:
        emit(args, result, ['dry run (nothing changed); with --yes this would:'] + ['  ' + x for x in steps] +
             ['the plugin does not commit: commit the moved folder and %s yourself' % artifact_queue.SETTINGS_NAME.replace(os.sep, '/')])
        return 0
    data = {}
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            raise Fail(2, '%s cannot be read as a JSON object' % artifact_queue.SETTINGS_NAME.replace(os.sep, '/'))
    ctx = Ctx.__new__(Ctx)
    ctx.root = root
    with locked(ctx):
        if has_old:
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            if new_dir.is_dir():
                new_dir.rmdir()
            shutil.move(str(old_dir), str(new_dir))
            parent = old_dir.parent
            while parent != root / 'docs' and parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        if new_rel == artifact_queue.DEFAULT_RECORD_REL:
            data.pop('record_dir', None)
        else:
            data['record_dir'] = new_rel
        if data:
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        elif settings.is_file():
            settings.unlink()
    result['moved'] = has_old
    emit(args, result, ['moved the record: %s/ -> %s/' % (old_rel, new_rel), 'commit the moved folder and %s when you choose (the plugin never commits)'
                        % artifact_queue.SETTINGS_NAME.replace(os.sep, '/')])
    return 0


def cmd_path(args):
    ctx, _rec = load_for_read(args)
    emit(args, {'record_dir': str(ctx.record_dir), 'worktree': str(ctx.record_dir)}, str(ctx.record_dir))
    return 0


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------

def build_parser():
    j = argparse.ArgumentParser(add_help=False)
    j.add_argument('--json', dest='json_out', action='store_true', help='machine-readable output')
    w = argparse.ArgumentParser(add_help=False, parents=[j])
    w.add_argument('--no-push', action='store_true', help='accepted for compatibility; does nothing')
    w.add_argument('--push', action='store_true', help='accepted for compatibility; does nothing (prints a note)')

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
    s.add_argument('--force', action='store_true', help='reuse the key of a retired feature (R4.35)')
    s.add_argument('--project', help='project name when init runs first (default: the repository name)')
    init_opts(s)
    s.set_defaults(func=cmd_feature_new)

    s = sub.add_parser('task-add', parents=[w], help='add a task; prints its ID')
    s.add_argument('--owner', required=True, help='a feature key, or project')
    s.add_argument('--item', required=True)
    s.add_argument('--detail', required=True)
    s.add_argument('--expected', required=True)
    s.add_argument('--basis', help='what sets the estimate, at most 80 characters (open statuses only)')
    s.add_argument('--app')
    s.add_argument('--status', default='To do')
    s.add_argument('--prefix')
    s.add_argument('--release', action='store_true', help='this task is a release; it gets the next number, RELEASE-n (R5.40, R5.45)')
    s.add_argument('--phase', action='append', metavar='NAME=HH:MM-HH:MM',
                   help='a release phase (agents, join, ci, merge), repeatable; "" clears them')
    s.add_argument('--risk', metavar='LABEL=MINUTES', help='the named risk of a release, for example "+1 fix round=10"; "" clears it')
    s.add_argument('--rides', metavar='ID', help='the release this task rides, its task ID or RELEASE-n (a Running or Built task needs one, R5.47); "" clears it')
    s.add_argument('--no-release', metavar='REASON', help='this task ships nothing (a publish, a study, a cleanup), at most 80 characters; it rides no release and is never Built (R5.47a); "" clears it')
    s.add_argument('--waits-on', metavar='owner|work', help='who a Waiting or On hold task waits on: owner (it shows under Needs you) or work (other work, the default); "" clears it (R5.34a)')
    s.add_argument('--started', metavar='"DD Mon ~HH:MM"|HH:MM', help='when work on the task began, in the project time zone; it is where an open task\'s bar starts on the timeline and must be before Expected; "" clears it (R5.48)')
    s.set_defaults(func=cmd_task_add)

    s = sub.add_parser('set-task-status', parents=[w], help='change one task')
    s.add_argument('id')
    s.add_argument('status')
    s.add_argument('--item', help='a corrected task title, at most 80 characters; recorded in the History of a feature task')
    s.add_argument('--detail')
    s.add_argument('--expected')
    s.add_argument('--basis', help='what sets the estimate; "" clears it (open statuses only)')
    s.add_argument('--history')
    s.add_argument('--release', action='store_true', help='this task is a release; it gets the next number, RELEASE-n (R5.40, R5.45)')
    s.add_argument('--phase', action='append', metavar='NAME=HH:MM-HH:MM',
                   help='a release phase (agents, join, ci, merge), repeatable; "" clears them')
    s.add_argument('--risk', metavar='LABEL=MINUTES', help='the named risk of a release, for example "+1 fix round=10"; "" clears it')
    s.add_argument('--rides', metavar='ID', help='the release this task rides, its task ID or RELEASE-n (a Running or Built task needs one, R5.47); "" clears it')
    s.add_argument('--no-release', metavar='REASON', help='this task ships nothing (a publish, a study, a cleanup), at most 80 characters; it rides no release and is never Built (R5.47a); "" clears it')
    s.add_argument('--waits-on', metavar='owner|work', help='who a Waiting or On hold task waits on: owner (it shows under Needs you) or work (other work, the default); "" clears it (R5.34a)')
    s.add_argument('--started', metavar='"DD Mon ~HH:MM"|HH:MM', help='when work on the task began, in the project time zone; it is where an open task\'s bar starts on the timeline and must be before Expected; "" clears it (R5.48)')
    s.add_argument('--into', metavar='ID', help='with Dropped: the task that took the work, its task ID or RELEASE-n; required for a release (R5.49)')
    s.add_argument('--reason', help='with Dropped: why, at most 80 characters; needed when --into is not given (R5.49)')
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
    s.add_argument('--record', help='the record folder (docs/artifacts by default; or the repository containing it)')
    s.set_defaults(func=cmd_check)

    s = sub.add_parser('pending', parents=[j], help='Full Progress to publish (with its publish copy) and queued events; exit 1 when any')
    s.add_argument('--refresh', action='store_true', help='list Full Progress even when unchanged (the hourly publish, R9.8)')
    s.set_defaults(func=cmd_pending)

    s = sub.add_parser('mark-published', parents=[w], help='record the URL and the hash of the committed render of Full Progress')
    s.add_argument('key')
    s.add_argument('--url', required=True)
    s.set_defaults(func=cmd_mark_published)

    s = sub.add_parser('mark-deferred', parents=[w], help='record that claude.ai refused the publish for its daily limit; pending stops asking until then')
    s.add_argument('key')
    s.add_argument('--until', required=True, metavar='ISO', help='when the limit resets, an ISO time with an offset')
    s.set_defaults(func=cmd_mark_deferred)

    s = sub.add_parser('retire', parents=[w], help='remove a finished feature artifact and its content, keeping its tasks and decisions (R4.31 to R4.36)')
    s.add_argument('key', help='the feature key')
    s.add_argument('--yes', action='store_true', help='do it; without it, list what would be deleted')
    s.set_defaults(func=cmd_retire)

    s = sub.add_parser('mark-deleted', parents=[w],
                       help='record that the owner confirmed and the session deleted an old claude.ai page of a feature artifact')
    s.add_argument('key', nargs='?', help='the feature key of the retired page (checked against the list)')
    s.add_argument('--url', required=True)
    s.add_argument('--gone', action='store_true', help='the page no longer exists (404)')
    s.set_defaults(func=cmd_mark_deleted)

    s = sub.add_parser('worktree', parents=[j], help='print the record folder, <root>/<record_dir> (R4.24)')
    s.set_defaults(func=cmd_worktree)

    s = sub.add_parser('queue', parents=[j], help='show or clear queued events')
    s.add_argument('action', choices=['list', 'clear'])
    s.add_argument('--id')
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser('migrate', parents=[j], help='copy the old record worktree into the record folder when newer (R4.24); idempotent')
    s.set_defaults(func=cmd_migrate)

    s = sub.add_parser('push', parents=[j], help='removed: exits 1 (R4.28)')
    s.add_argument('--default-branch')
    s.set_defaults(func=cmd_push)

    s = sub.add_parser('commit', parents=[w], help='removed: exits 1 (R4.28)')
    s.add_argument('--retry', action='store_true', help='accepted for compatibility')
    s.add_argument('--message')
    s.set_defaults(func=cmd_commit)

    s = sub.add_parser('move-record', parents=[j], help='move the record folder to another folder under docs/ and set record_dir; dry run without --yes')
    s.add_argument('new_dir', help='the new record folder, relative to the repository, under docs/ (docs/artifacts is the default)')
    s.add_argument('--yes', action='store_true', help='do it (without it, only print what would happen)')
    s.set_defaults(func=cmd_move_record)

    s = sub.add_parser('promote-to-spec', parents=[j], help="write a feature artifact's decided content to docs/features/<feature>/spec.md (DOCSPEC R4.10); dry run without --apply, merges into an existing spec")
    s.add_argument('key', help='the feature artifact key')
    s.add_argument('--feature', help='the feature folder name under docs/features/ (default: the key)')
    s.add_argument('--apply', action='store_true', help='write (or merge into) the spec; without it only the plan and, for an existing spec, a diff are printed')
    s.add_argument('--yes', action='store_true', help='same as --apply')
    s.set_defaults(func=cmd_promote_to_spec)

    s = sub.add_parser('path', parents=[j], help='print the record folder, <root>/<record_dir>')
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
