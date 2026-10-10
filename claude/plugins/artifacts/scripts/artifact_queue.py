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
