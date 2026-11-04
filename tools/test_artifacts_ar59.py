#!/usr/bin/env python3
"""Regression tests for the artifacts plugin review findings F20 to F27 (AR59).

Run:  python -I tools/test_artifacts_ar59.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import json
import os
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'artifacts')
SCRIPTS = os.path.join(PLUGIN, 'scripts')
sys.path.insert(0, SCRIPTS)

import artifact_hourly as H  # noqa: E402
import artifact_queue as Q  # noqa: E402
import hook_after_command as A  # noqa: E402
import hook_session_start as S  # noqa: E402
import project_artifacts as P  # noqa: E402
import publish_hourly as PH  # noqa: E402
import render_artifacts as R  # noqa: E402

TESTS = []


def case(fn):
    TESTS.append(fn)
    return fn


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


@case
def f20_deferred_holds_hourly_and_release():
    manifest = {'full_progress_artifact': {'url': 'u', 'published_at': '2026-11-04T10:00:00+00:00',
                                           'deferred_until': '2026-11-05T00:00:00+00:00'}}
    now = utc(2026, 11, 4, 11, 30)
    assert H.hourly_due(manifest, now) is None
    tasks = [{'id': 'A1', 'release': True, 'status': 'Running', 'changed': '2026-11-04T11:00:00+00:00'}]
    assert H.release_changes(tasks, manifest, now) == []
    assert PH.reasons(manifest, tasks, now) == []
    later = utc(2026, 11, 5, 1, 0)       # deferral over: asks again
    assert H.hourly_due(manifest, later) is not None
    assert PH.reasons(manifest, tasks, later)


@case
def f21_concurrent_queue_writes_keep_every_event():
    with tempfile.TemporaryDirectory() as root:
        code = ('import sys; sys.path.insert(0, %r); import artifact_queue as Q\n'
                'for i in range(5): Q.append_event(%r, "T%%s-%%d" %% (sys.argv[1], i), "Running", "e")\n'
                % (SCRIPTS, root))
        procs = [subprocess.Popen([sys.executable, '-c', code, str(n)], stderr=subprocess.PIPE) for n in range(8)]
        errs = [p.communicate()[1] for p in procs]
        assert not any(errs), errs
        assert len(Q.read_queue(root)) == 40, len(Q.read_queue(root))


@case
def f22_dd_mon_takes_year_nearest_now():
    now = datetime(2027, 1, 1, 8, 0, tzinfo=timezone.utc)
    assert P.parse_started('31 Dec ~22:00', now).startswith('2026-12-31T22:00')
    phases = P.parse_phases(['ci=31 Dec 22:00-31 Dec 23:00'], now)
    assert phases[0]['start'].startswith('2026-12-31T22:00'), phases
    assert P.parse_started('22:00', now).startswith('2027-01-01T22:00')


@case
def f23_classify_ignores_quotes_and_unproven_exit_codes():
    M = A.MERGED
    create = [('Running', 'gh pr create')]
    assert A.classify('git commit -m "docs: explain; gh pr merge 12 later"', 0) == []
    assert A.classify('echo "next step && gh pr create --fill"', 0) == []
    assert A.classify('gh pr merge 12 --squash || true', 0) == []
    assert A.classify('gh pr merge 12 --squash; echo done', 0) == []
    assert A.classify('gh pr merge 12 --squash', 0) == [(M, 'gh pr merge')]
    assert A.classify('gh pr merge 12 --squash && echo done', 0) == [(M, 'gh pr merge')]
    assert A.classify('git push && gh pr create --fill', 0) == create
    assert A.classify('gh pr merge 12', 1) == []
    assert A.classify('gh run watch 5; echo done', 0) == []
    assert A.classify('gh run watch 5', 1) == [('Failed', 'gh run watch failed')]


@case
def f24_open_pr_blocks_merged_suggestion():
    prs = [{'headRefName': 'LOG1-login-form', 'state': 'MERGED', 'mergedAt': 'x'},
           {'headRefName': 'LOG1-fix-round', 'state': 'OPEN'}]
    assert S.outcomes_by_task(prs)['LOG1'] == {'merged', 'open'}
    with tempfile.TemporaryDirectory() as root:
        S.list_pull_requests = lambda r: (prs, None)
        S.load_registry = lambda r, b: {'tasks': [{'id': 'LOG1', 'status': 'Running'}]}
        S.catch_up(root, {})
        assert Q.read_queue(root) == [], Q.read_queue(root)


@case
def f25_far_past_expected_is_not_overdue():
    manifest = {'timezone': 'UTC'}
    now = utc(2026, 11, 4, 10, 0)
    assert H.overdue_tasks([{'id': 'L3', 'status': 'To do', 'expected': '15 Jun'}], manifest, now) == []
    assert len(H.overdue_tasks([{'id': 'L3', 'status': 'To do', 'expected': '01 Nov'}], manifest, now)) == 1
    task = {'id': 'L3', 'status': 'Running', 'expected': '15 Jun', 'no_release': 'reason'}
    assert R._other_row(task, now) is None


@case
def f26_feb_29_parses_in_a_leap_year():
    assert H.expected_datetime('29 Feb ~10:00', datetime(2028, 3, 1, 12)) == datetime(2028, 2, 29, 10, 0)
    assert R._expected_datetime('29 Feb', datetime(2028, 3, 1, 12)) == datetime(2028, 2, 29, 23, 59)
    od = H.overdue_tasks([{'id': 'L', 'status': 'To do', 'expected': '29 Feb ~10:00'}], {'timezone': 'UTC'},
                         utc(2028, 3, 1, 12, 0))
    assert len(od) == 1


@case
def f27_repo_root_reads_utf8_path():
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, 'josé')
        os.mkdir(d)
        subprocess.run(['git', 'init', '-q', d], check=True)
        env = dict(os.environ, LC_ALL='C', PYTHONCOERCECLOCALE='0', PYTHONUTF8='0')
        code = ('import sys; sys.path.insert(0, %r); import artifact_queue as Q; r = Q.repo_root(None); '
                'sys.stdout.buffer.write((r or "NONE").encode("utf-8", "replace"))' % SCRIPTS)
        out = subprocess.run([sys.executable, '-c', code], env=env, cwd=d, capture_output=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.decode('utf-8').endswith('josé'), out.stdout


@case
def hooks_json_keeps_a_block_exit_code():
    with open(os.path.join(PLUGIN, 'hooks', 'hooks.json'), encoding='utf-8') as f:
        data = json.load(f)
    for groups in data['hooks'].values():
        for g in groups:
            for h in g['hooks']:
                c = h['command']
                assert '||' not in c and c.startswith('if command -v python3'), c


def main():
    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
            passed += 1
        except Exception:
            failed += 1
            print('FAIL %s' % fn.__name__)
            traceback.print_exc()
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
