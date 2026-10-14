#!/usr/bin/env python3
"""Hourly and on-change publishing of Full Progress (ARTIFACTSPEC R9.8 to R9.11, R6.12).

Pure helpers shared by hook_end_of_turn.py, project_artifacts.py (`check`, `pending`) and
publish_hourly.py. They only read: the manifest's `full_progress_artifact.published_at` and the
registry's tasks. Standard library only.

Seam for tests: CLAUDE_ARTIFACTS_NOW (ISO) overrides the clock, as in project_artifacts.py.
"""
import os
import re
from datetime import datetime, timezone

STALE_MINUTES = 60      # R9.8: Full Progress is published at least this often while a project is live
OPEN_STATUSES = ('Running', 'Waiting', 'To do', 'Needs you', 'On hold')
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


def minutes_since_publish(manifest, now=None):
    at = published_at(manifest)
    if at is None:
        return None
    return int(((now or now_instant()) - at).total_seconds() // 60)


def hourly_due(manifest, now=None):
    """R9.8: minutes since the last publish when that is over STALE_MINUTES, else None."""
    mins = minutes_since_publish(manifest, now)
    return mins if mins is not None and mins > STALE_MINUTES else None


def is_release(task):
    r = task.get('release') if isinstance(task, dict) else None
    return r is True or (isinstance(r, int) and not isinstance(r, bool))


def release_changes(tasks, manifest):
    """R9.9: release tasks whose status or phases changed after the last publish (their `changed` stamp,
    which the script sets on every change, is later than `published_at`). [] when never published."""
    at = published_at(manifest)
    if at is None:
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
            return None
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
        if when is not None and when < ref:
            out.append((t, when))
    return out


def overdue_text(task):
    return '%s (%s) is %s but its Expected "%s" has passed' % (
        task.get('id'), task.get('item', ''), task.get('status'), task.get('expected'))
