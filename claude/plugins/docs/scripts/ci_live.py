#!/usr/bin/env python3
"""ci_live: live CI runs for open releases and tasks in Full Progress (DS295, R5.39 to R5.41).

`refresh(tasks, runner, now_iso)` asks gh for the workflow runs of a pull request's head commit, of its merge commit
and of a release tag, and stores them on the task as `ci_runs`. The render reads only what is stored. A missing gh,
no network or any error keeps the runs stored last. Tests pass a `runner`; `CLAUDE_ARTIFACTS_NO_GH=1` skips the fetch.
Standard library only.
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone

RUN_FIELDS = 'name,status,conclusion,url,createdAt,updatedAt,headBranch,event'
CLOSED = ('Live', 'Dropped')
STATES = ('queued', 'running', 'passed', 'failed', 'cancelled')
FAILED = ('failure', 'timed_out', 'startup_failure', 'action_required')


def skipped() -> bool:
    return os.environ.get('CLAUDE_ARTIFACTS_NO_GH') == '1'


def default_runner(args):
    """(returncode, stdout) of `gh <args>`; (1, '') when gh is missing or slow."""
    try:
        r = subprocess.run(['gh'] + list(args), capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ''
    return r.returncode, r.stdout


def _json(runner, args):
    """Parsed JSON of a gh call, or None on any failure."""
    try:
        rc, out = runner(args)
        return json.loads(out) if rc == 0 and out and out.strip() else None
    except Exception:
        return None


def state_of(status, conclusion) -> str:
    """queued / running / passed / failed / cancelled from gh's status and conclusion."""
    if status == 'completed':
        if conclusion == 'cancelled':
            return 'cancelled'
        return 'failed' if conclusion in FAILED else 'passed'
    return 'running' if status == 'in_progress' else 'queued'


def parse_runs(data, kind) -> list:
    """The stored form of a `gh run list --json` array; a malformed item is dropped."""
    out = []
    for r in data if isinstance(data, list) else []:
        if not isinstance(r, dict) or not r.get('name') or not r.get('url'):
            continue
        out.append({'name': str(r['name']), 'state': state_of(r.get('status'), r.get('conclusion')), 'url': str(r['url']),
                    'created': str(r.get('createdAt') or ''), 'updated': str(r.get('updatedAt') or ''),
                    'branch': str(r.get('headBranch') or ''), 'event': str(r.get('event') or ''), 'kind': kind})
    return out


def runs_for(runner, sha, kind) -> list:
    data = _json(runner, ['run', 'list', '--commit', sha, '--json', RUN_FIELDS])
    return None if data is None else parse_runs(data, kind)


def pr_commits(runner, number):
    """(head sha, merge commit sha or '') of a pull request, or None when gh cannot say."""
    data = _json(runner, ['pr', 'view', str(number), '--json', 'headRefOid,mergeCommit'])
    if not isinstance(data, dict) or not data.get('headRefOid'):
        return None
    merge = data.get('mergeCommit')
    return data['headRefOid'], (merge.get('oid') or '') if isinstance(merge, dict) else ''


def wants_runs(task) -> bool:
    return isinstance(task, dict) and task.get('status') not in CLOSED and bool(task.get('id'))


def tag_of(task) -> str:
    return str(task.get('tag') or task.get('version_tag') or '')


def refresh(tasks, runner=None, now_iso='') -> int:
    """Store `ci_runs` on every open task that has a pull request, a release tag or a pushed `<id>-*` branch.
    Returns how many tasks were updated. A task whose fetch failed keeps what it had."""
    if skipped():
        return 0
    runner = runner or default_runner
    open_tasks = [t for t in tasks if wants_runs(t)]
    if not open_tasks:
        return 0
    recent = {}                        # one call for the branch and tag runs of every task

    def all_runs():
        if 'v' not in recent:
            data = _json(runner, ['run', 'list', '--limit', '100', '--json', RUN_FIELDS])
            recent['v'] = parse_runs(data, 'branch') if data is not None else None
        return recent['v']

    by_pr, n = {}, 0
    for t in open_tasks:
        runs, ok = [], False
        pr = t.get('pr') if isinstance(t.get('pr'), int) else None
        if pr:
            if pr not in by_pr:
                got = pr_commits(runner, pr)
                by_pr[pr] = None if got is None else (runs_for(runner, got[0], 'pr'),
                                                      runs_for(runner, got[1], 'merge') if got[1] else [])
            if by_pr[pr] and by_pr[pr][0] is not None:
                runs += by_pr[pr][0] + (by_pr[pr][1] or [])
                ok = True
        branch_runs = all_runs()
        if branch_runs is not None:
            tag = tag_of(t)
            for r in branch_runs:
                if tag and r['branch'] == tag:
                    runs.append(dict(r, kind='tag'))
                    ok = True
                elif not pr and r['branch'].startswith(str(t['id']) + '-'):
                    runs.append(dict(r, kind='branch'))
                    ok = True
        if not ok:
            continue                   # keep the last stored runs and their fetched time
        seen, uniq = set(), []
        for r in runs:
            if r['url'] not in seen:
                seen.add(r['url'])
                uniq.append(r)
        uniq.sort(key=lambda r: r['created'])
        entry = {'fetched_at': now_iso, 'runs': uniq}
        if t.get('ci_runs') != entry:
            t['ci_runs'] = entry
            n += 1
    return n


def _dt(text):
    try:
        return datetime.fromisoformat(str(text).replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def clock(text) -> str:
    d = _dt(text)
    return d.strftime('%H:%M') if d else '--:--'


def span(seconds) -> str:
    s = max(0, int(seconds))
    return '%dm %02ds' % (s // 60, s % 60) if s >= 60 else '%ds' % s


def timing(run, fetched_at) -> str:
    """`HH:MM UTC` plus the duration of a finished run or the elapsed time of a running one (as of fetch)."""
    start = _dt(run.get('created'))
    if start is None:
        return clock(run.get('created'))
    end = _dt(run.get('updated')) if run.get('state') in ('passed', 'failed', 'cancelled') else _dt(fetched_at)
    tail = ''
    if end is not None and run.get('state') != 'queued':
        tail = ' %s %s' % ('elapsed' if run.get('state') == 'running' else 'in', span((end - start).total_seconds()))
    return '%s UTC%s' % (start.strftime('%H:%M'), tail)
