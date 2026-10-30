"""The queue of status events waiting for the session (ARTIFACTSPEC §8.1).

Shared by the hooks and project_artifacts.py. The queue lives at
<repo>/.claude/artifacts-queue.json, is gitignored, and is never part of the
record. Standard library only.
"""
import json
import os
import subprocess
from datetime import datetime, timezone

QUEUE_NAME = os.path.join('.claude', 'artifacts-queue.json')
WORKTREE_ENV = 'LUISMC_ARTIFACTS_WORKTREE'                       # R4.24
LOCAL_NAME = os.path.join('.claude', 'artifacts-local.json')     # git-ignored, machine-specific
DEFAULT_WORKTREE = os.path.join('.claude', 'worktrees', 'artifacts-record')


class WorktreeSettingError(ValueError):
    """The record worktree setting is not an absolute, usable path."""


SETTINGS_NAME = os.path.join('.claude', 'artifacts.json')       # committed, per project
DEFAULT_RECORD_REL = 'docs/artifacts'


class RecordDirError(ValueError):
    """The record_dir setting is not a relative folder under docs/."""


def check_record_rel(raw, source='record_dir'):
    """The normalized record folder (forward slashes) for a candidate value; RecordDirError when it is not
    a relative path strictly under docs/."""
    if not isinstance(raw, str) or not raw.strip() or '\0' in raw:
        raise RecordDirError('%s must be a relative folder under docs/' % source)
    text = raw.strip().replace('\\', '/')
    if text.startswith('/') or (len(text) > 1 and text[1] == ':'):
        raise RecordDirError('%s must be relative, got "%s"' % (source, raw))
    parts = [p for p in text.split('/') if p not in ('', '.')]
    if '..' in parts:
        raise RecordDirError('%s must not contain "..", got "%s"' % (source, raw))
    if len(parts) < 2 or parts[0] != 'docs':
        raise RecordDirError('%s must be a folder under docs/ (for example docs/work/artifacts), got "%s"' % (source, raw))
    return '/'.join(parts)


def record_rel(root):
    """The record folder relative to the repository root: "record_dir" in <root>/.claude/artifacts.json,
    else docs/artifacts. Raises RecordDirError when the setting is set and unusable."""
    path = os.path.join(root, SETTINGS_NAME)
    if not os.path.isfile(path):
        return DEFAULT_RECORD_REL
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise RecordDirError('%s cannot be read: %s' % (SETTINGS_NAME.replace(os.sep, '/'), e))
    if not isinstance(data, dict):
        raise RecordDirError('%s must hold a JSON object' % SETTINGS_NAME.replace(os.sep, '/'))
    if 'record_dir' not in data:
        return DEFAULT_RECORD_REL
    return check_record_rel(data['record_dir'], '.claude/artifacts.json record_dir')


def record_rel_safe(root):
    """record_rel for the hooks: an unusable setting falls back to the default, never raises."""
    try:
        return record_rel(root)
    except RecordDirError:
        return DEFAULT_RECORD_REL


def _same_path(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _inside(child, parent):
    c, p = os.path.normcase(os.path.realpath(child)), os.path.normcase(os.path.realpath(parent))
    return c == p or c.startswith(p.rstrip('\\/') + os.sep)


def default_worktree(root):
    return os.path.join(root, DEFAULT_WORKTREE)


def record_worktree(root):
    """Where the retired record worktree was (R4.24); used only to migrate its record once (AR50).
    The record now lives in docs/artifacts/ of the working tree and the plugin never commits it.


    The environment variable LUISMC_ARTIFACTS_WORKTREE first, else "record_worktree" in
    <root>/.claude/artifacts-local.json, else <root>/.claude/worktrees/artifacts-record.
    A set value must be an absolute path outside the repository's .git and not holding the
    repository; anything else raises WorktreeSettingError.
    """
    raw, source = os.environ.get(WORKTREE_ENV), WORKTREE_ENV
    if not raw:
        raw, source = None, None
        path = os.path.join(root, LOCAL_NAME)
        if os.path.isfile(path):
            try:
                with open(path, encoding='utf-8') as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as e:
                raise WorktreeSettingError('%s cannot be read: %s' % (LOCAL_NAME, e))
            if not isinstance(data, dict):
                raise WorktreeSettingError('%s must hold a JSON object' % LOCAL_NAME)
            if 'record_worktree' in data:
                raw, source = data['record_worktree'], LOCAL_NAME + ' record_worktree'
    if raw is None:
        return default_worktree(root)
    if not isinstance(raw, str) or not raw.strip() or '\0' in raw:
        raise WorktreeSettingError('%s must be a path' % source)
    raw = raw.strip()
    if not os.path.isabs(raw) or (os.name == 'nt' and not os.path.splitdrive(raw)[0]):
        raise WorktreeSettingError('%s must be an absolute path, got "%s"' % (source, raw))
    path = os.path.normpath(raw)
    if _inside(root, path):
        raise WorktreeSettingError('%s "%s" is or contains the repository' % (source, raw))
    if _inside(path, os.path.join(root, '.git')):
        raise WorktreeSettingError('%s "%s" is inside .git' % (source, raw))
    return path


def repo_root(start=None):
    """Top of the git checkout containing `start` (default: cwd), or None."""
    try:
        out = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=start or os.getcwd(),
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def queue_path(root):
    return os.path.join(root, QUEUE_NAME)


def read_queue(root):
    """List of events; [] when the file is missing or unreadable."""
    try:
        with open(queue_path(root), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return data.get('events', []) if isinstance(data, dict) else []


def _write(root, events):
    p = queue_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'events': events}, f, indent=1)
        f.write('\n')
    os.replace(tmp, p)


def append_event(root, task_id, suggested_status, event, command=''):
    """Queue one event; an identical (id, status, event) entry is not added twice."""
    events = read_queue(root)
    if any(e.get('id') == task_id and e.get('suggested_status') == suggested_status
           and e.get('event') == event for e in events):
        return events
    events.append({'id': task_id, 'suggested_status': suggested_status, 'event': event,
                   'command': command[:200],
                   'time': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')})
    _write(root, events)
    return events


def remove_events(root, task_id=None):
    """Remove the events of one task, or all events when task_id is None."""
    events = [] if task_id is None else [e for e in read_queue(root) if e.get('id') != task_id]
    _write(root, events)
    return events
