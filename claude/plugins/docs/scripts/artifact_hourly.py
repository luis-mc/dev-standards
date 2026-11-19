#!/usr/bin/env python3
"""Hourly and on-change publishing of Full Progress (ARTIFACTSPEC R9.8 to R9.11, R6.14).

Pure helpers shared by hook_end_of_turn.py, project_artifacts.py (`check`, `pending`) and
publish_hourly.py. They only read: the manifest's `full_progress_artifact.published_at` and the
registry's tasks. Standard library only.

Seam for tests: CLAUDE_ARTIFACTS_NOW (ISO) overrides the clock, as in project_artifacts.py.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

STALE_MINUTES = 60      # R9.8: Full Progress is published at least this often while a project is live
SETTLE_DEFAULT = 60     # R9.13 (AR72): seconds the record must be quiet, and Full Progress unpublished, before a publish is asked for
FAR_PAST = timedelta(days=42)   # F25
OPEN_STATUSES = ('Running', 'Waiting', 'To do', 'Needs you', 'On hold')
WORK_OPEN_STATUSES = ('Running', 'Waiting', 'Needs you')     # R9.8: the hourly fail-safe applies only then
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
EXPECTED_RE = re.compile(r'^(0[1-9]|[12][0-9]|3[01]) (' + '|'.join(MONTHS) + r')(?: ~([01][0-9]|2[0-3]):([0-5][0-9]))?(?:; \S.*)?$')


def parse_iso(text):
    try:
        dt = datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def now_instant():
    forced = os.environ.get('CLAUDE_ARTIFACTS_NOW')
    if forced:
        dt = parse_iso(forced)
        if dt is not None:
            return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def full_progress(manifest):
    fp = manifest.get('full_progress_artifact') if isinstance(manifest, dict) else None
    return fp if isinstance(fp, dict) else {}


def published_at(manifest):
    """When Full Progress was last published, as an aware datetime; None when it never was."""
    fp = full_progress(manifest)
    if not (fp.get('url') or fp.get('published_sha256')):
        return None
    return parse_iso(fp.get('published_at')) if fp.get('published_at') else None


def is_deferred(manifest, now=None):
    """R9.7: True while Full Progress's `deferred_until` is in the future."""
    until = parse_iso(full_progress(manifest).get('deferred_until')) if full_progress(manifest).get('deferred_until') else None
    return until is not None and until > (now or now_instant())


def minutes_since_publish(manifest, now=None):
    at = published_at(manifest)
    if at is None:
        return None
    return int(((now or now_instant()) - at).total_seconds() // 60)


def work_open(tasks):
    """R9.8 (D20): True when a task is Running, Waiting or Needs you."""
    return any(isinstance(t, dict) and t.get('status') in WORK_OPEN_STATUSES for t in tasks or ())


def hourly_due(manifest, now=None, tasks=None):
    """R9.8: minutes since the last publish when that is over STALE_MINUTES and work is open, else None.
    `tasks` None skips the open-work test (callers that have the registry pass it)."""
    if is_deferred(manifest, now):
        return None
    if tasks is not None and not work_open(tasks):
        return None
    mins = minutes_since_publish(manifest, now)
    return mins if mins is not None and mins > STALE_MINUTES else None


def is_release(task):
    r = task.get('release') if isinstance(task, dict) else None
    return r is True or (isinstance(r, int) and not isinstance(r, bool))


def release_changes(tasks, manifest, now=None):
    """R9.9: release tasks whose status or phases changed after the last publish (their `changed` stamp,
    which the script sets on every change, is later than `published_at`). [] when never published."""
    at = published_at(manifest)
    if at is None or is_deferred(manifest, now):
        return []
    out = []
    for t in tasks:
        if not is_release(t):
            continue
        changed = parse_iso(t.get('changed')) if t.get('changed') else None
        if changed is not None and changed > at:
            out.append(t)
    return out


def local_now(manifest, now=None):
    """Naive wall-clock time of `now` in the project's zone (manifest `timezone`), else the machine's."""
    instant = now or now_instant()
    zone = manifest.get('timezone') if isinstance(manifest, dict) else None
    if zone and not os.environ.get('CLAUDE_ARTIFACTS_NO_ZONEINFO'):
        try:
            from zoneinfo import ZoneInfo
            return instant.astimezone(ZoneInfo(zone)).replace(tzinfo=None)
        except Exception:
            pass
    at = published_at(manifest)
    if at is not None and at.utcoffset() is not None and not zone:
        return instant.astimezone(timezone(at.utcoffset())).replace(tzinfo=None)
    return instant.astimezone().replace(tzinfo=None)


def expected_datetime(text, ref):
    """Naive datetime of an Expected value ('DD Mon' ends at 23:59, 'DD Mon ~HH:MM'); year nearest `ref`."""
    m = EXPECTED_RE.match(str(text or ''))
    if not m:
        return None
    day, month = int(m.group(1)), MONTHS.index(m.group(2)) + 1
    hour, minute = (int(m.group(3)), int(m.group(4))) if m.group(3) else (23, 59)
    best = None
    for year in (ref.year - 1, ref.year, ref.year + 1):
        try:
            cand = datetime(year, month, day, hour, minute)
        except ValueError:
            continue
        if best is None or abs(cand - ref) < abs(best - ref):
            best = cand
    return best


def overdue_tasks(tasks, manifest, now=None):
    """DL-63: open rows whose Expected time is in the past. [(task, expected datetime)]"""
    ref = local_now(manifest, now)
    out = []
    for t in tasks:
        if not isinstance(t, dict) or t.get('status') not in OPEN_STATUSES:
            continue
        when = expected_datetime(t.get('expected'), ref)
        if when is not None and ref - when > FAR_PAST and EXPECTED_RE.match(str(t.get('expected'))):
            continue      # F25: over six weeks back means a plan for the next occurrence, not an overdue row
        if when is not None and when < ref:
            out.append((t, when))
    return out


def overdue_text(task):
    return '%s (%s) is %s but its Expected "%s" has passed' % (
        task.get('id'), task.get('item', ''), task.get('status'), task.get('expected'))


def settle_sec(root):
    """R9.13: `full_progress.settle_sec` of <root>/.delivery/config.json; 60 when unset or not a number >= 0.
    Seam for tests: CLAUDE_ARTIFACTS_SETTLE_SEC overrides it."""
    forced = os.environ.get('CLAUDE_ARTIFACTS_SETTLE_SEC')
    if forced:
        try:
            return max(0.0, float(forced))
        except ValueError:
            pass
    try:
        with open(os.path.join(str(root), '.delivery', 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        v = cfg['full_progress']['settle_sec']
    except (OSError, ValueError, KeyError, TypeError):
        return SETTLE_DEFAULT
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else SETTLE_DEFAULT


STATE_REL = os.path.join('.claude', 'artifacts-stop-state.json')


def stamp_settle(root, field, instant=None):
    """R9.13: remember, to the second, when the record last changed ('write') or Full Progress was last published
    ('publish'), under the key "settle" of the stop-state file (the record's own stamps are to the minute).
    Never raises: a state that cannot be written only makes the window coarser."""
    path = os.path.join(str(root), STATE_REL)
    try:
        try:
            with open(path, encoding='utf-8') as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        entry = state.get('settle') if isinstance(state.get('settle'), dict) else {}
        entry[field] = (instant or now_instant()).isoformat(timespec='seconds')
        state['settle'] = entry
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = '%s.%d.tmp' % (path, os.getpid())
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except OSError:
        pass


def read_settle(root, field):
    """The ISO text stamp_settle stored for `field`, '' when none."""
    try:
        with open(os.path.join(str(root), STATE_REL), encoding='utf-8') as f:
            v = json.load(f)['settle'][field]
    except (OSError, ValueError, KeyError, TypeError):
        return ''
    return v if isinstance(v, str) else ''


def settle_wait(manifest, last_write, window, now=None, last_publish=''):
    """R9.13: (seconds still to wait, why) while a publish of Full Progress would be inside the settle window, else None.
    Inside it when the previous publish, or the record's last write (`last_write`, ISO text), is less than `window`
    seconds old. Never applies to the hourly fail-safe."""
    now = now or now_instant()
    best = None
    pub = published_at(manifest)
    if pub is not None and last_publish:
        pub = max(pub, parse_iso(last_publish) or pub)       # the stamp to the second, when there is one
    for at, why in ((pub, 'the previous publish'), (parse_iso(last_write) if last_write else None, 'the last record change')):
        if at is None:
            continue
        age = (now - at).total_seconds()
        left = window - age
        if age >= 0 and 0 < left and (best is None or left > best[0]):
            best = (int(left) + 1, why)
    return best
