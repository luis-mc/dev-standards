#!/usr/bin/env python3
"""Self-hosted runner job-completed hook (DELIVERYSPEC DL-90): free the job's CI slot and empty its work folder.

    runner_job_done.py [--log FILE] [--keep-work]

Set it as the runner's ACTIONS_RUNNER_HOOK_JOB_COMPLETED hook, next to runner_load_gate (the job-started hook). It
finds the slot held by this job (GITHUB_REPOSITORY, GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT, GITHUB_JOB), frees it, writes the
`released` line of the slot log (outcome `ran`), and empties the job's work folder (GITHUB_WORKSPACE, which must lie
inside a `_work` folder; the folder itself stays). A job that held no slot (machine layer off, or on_timeout=run) only
gets its work folder emptied. It always exits 0: a hook that fails here would fail a job that already finished.
Standard library only.
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import machine_slots as MS  # noqa: E402


def work_folder(env=None):
    """The job's checkout folder when it is safe to empty: inside a `_work` folder, and not `_work` itself."""
    env = os.environ if env is None else env
    path = env.get('GITHUB_WORKSPACE') or ''
    if not path:
        return None
    norm = os.path.abspath(path)
    parts = [p.lower() for p in norm.replace('\\', '/').split('/')]
    if '_work' not in parts or parts[-1] == '_work':
        return None
    return norm


def empty_folder(path):
    """Delete everything inside `path`. Returns the number of entries it could not remove."""
    failed = 0
    try:
        names = os.listdir(path)
    except OSError:
        return 0
    for name in names:
        full = os.path.join(path, name)
        try:
            if os.path.islink(full) or os.path.isfile(full):
                os.unlink(full)
            else:
                shutil.rmtree(full)
        except OSError:
            failed += 1
    return failed


def done(env=None, log=print, keep_work=False, outcome='ran'):
    """Free this job's slot(s) and empty its work folder. Returns {'freed': [slot numbers], 'work': path|None}."""
    env = os.environ if env is None else env
    freed = []
    ident = MS.ident_from_env(env)
    for lock in MS.find_held(ident):
        if MS.free_slot(lock, outcome):
            freed.append(lock['slot'])
            log('runner job done: freed slot %d of %s run %s job %s' % (lock['slot'], ident['repo'], ident['run_id'],
                                                                        ident['job']))
    if not freed:
        log('runner job done: this job held no slot')
    work = None if keep_work else work_folder(env)
    if work:
        bad = empty_folder(work)
        log('runner job done: emptied %s%s' % (work, ' (%d entries stay)' % bad if bad else ''))
    return {'freed': freed, 'work': work}


def main(argv=None):
    ap = argparse.ArgumentParser(prog='runner_job_done.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('--log')
    ap.add_argument('--keep-work', action='store_true')
    args = ap.parse_args(argv)
    path = args.log or os.environ.get('DELIVERY_GATE_LOG') or os.path.join(MS.machine_dir(), 'runner-gate.log')

    def log(line):
        line = '%s %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), line)
        print(line, flush=True)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass
    try:
        done(log=log, keep_work=args.keep_work)
    except Exception as exc:  # noqa: BLE001 - never fail a finished job
        log('runner job done: skipped (%s: %s)' % (type(exc).__name__, exc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
