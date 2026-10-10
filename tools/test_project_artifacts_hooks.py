#!/usr/bin/env python3
"""Tests for the three luismc-artifacts hooks (ARTIFACTSPEC 1.1.0 section 8, R13.2).

Feeds sample hook input to each hook in throwaway git repos (with a bare remote)
and asserts the queue, the exit code and the output, including R8.2, R8.4, R8.5,
R8.6, the CLAUDE_ARTIFACTS_HOOKS=off switch of section 12 and INV-4 (the hooks
never modify docs/artifacts/). project_artifacts.py and gh are replaced by
small Python stubs through CLAUDE_ARTIFACTS_SCRIPT and CLAUDE_ARTIFACTS_GH.

Run: python -I tools/test_project_artifacts_hooks.py
Standard library only. Prints "N passed, 0 failed" and exits 0 when all pass.
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'artifacts')
SCRIPTS = os.path.join(PLUGIN, 'scripts')
AFTER = os.path.join(SCRIPTS, 'hook_after_command.py')
STOP = os.path.join(SCRIPTS, 'hook_end_of_turn.py')
START = os.path.join(SCRIPTS, 'hook_session_start.py')

TESTS = []
INV4 = {'runs': 0, 'violations': []}
TMP_ROOT = tempfile.mkdtemp(prefix='hooks-test-')


def test(fn):
    TESTS.append(fn)
    return fn


def _rm_error(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def cleanup():
    shutil.rmtree(TMP_ROOT, onerror=_rm_error)


# --- fixtures -------------------------------------------------------------------------

def sh(args, cwd):
    p = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
                       + args, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError('git %s failed: %s' % (' '.join(args), p.stderr))
    return p.stdout


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


MANIFEST = {'spec': 'ARTIFACTSPEC 1.0.0', 'project': 'Demo', 'default_branch': 'main',
            'merged_status': 'Live', 'feature_artifacts': [], 'project_prefixes': ['AR']}
TASKS = [('AR5', 'Running'), ('AR6', 'Waiting'), ('AR7', 'To do'), ('AR8', 'Needs you'),
         ('AR9', 'Running'), ('AR10', 'Running'), ('AR11', 'Live'), ('AR13', 'Running')]
REGISTRY = {'spec': 'ARTIFACTSPEC 1.0.0', 'tasks': [{'id': i, 'owner': 'project', 'status': s, 'item': 'x'}
                                                    for i, s in TASKS]}
_counter = [0]


def make_repo(manifest=True, branch='AR5-x', merged_status='Live', manifest_on_origin_only=False,
              statuses=None):
    """A working clone with a bare remote. Returns the work directory. `statuses` replaces the
    registry's task statuses (a list of status strings) in the committed record."""
    _counter[0] += 1
    base = os.path.join(TMP_ROOT, 'r%d' % _counter[0])
    remote, work = os.path.join(base, 'remote.git'), os.path.join(base, 'work')
    os.makedirs(remote)
    os.makedirs(work)
    sh(['init', '-q', '--bare', '-b', 'main'], remote)
    sh(['init', '-q', '-b', 'main'], work)
    sh(['remote', 'add', 'origin', remote], work)
    write(os.path.join(work, 'README.md'), 'demo\n')
    sh(['add', '-A'], work)
    sh(['commit', '-q', '-m', 'readme'], work)
    if manifest:
        m = dict(MANIFEST, merged_status=merged_status)
        write(os.path.join(work, 'docs', 'artifacts', 'manifest.json'), json.dumps(m))
        registry = REGISTRY if statuses is None else dict(REGISTRY, tasks=[
            {'id': 'AR%d' % (20 + n), 'owner': 'project', 'status': s, 'item': 'x'}
            for n, s in enumerate(statuses)])
        write(os.path.join(work, 'docs', 'artifacts', 'registry.json'), json.dumps(registry))
        write(os.path.join(work, 'docs', 'artifacts', 'feature-demo.html'), '<title>Feature: Demo</title>\n')
        sh(['add', '-A'], work)
        sh(['commit', '-q', '-m', 'record'], work)
    sh(['push', '-q', 'origin', 'main'], work)
    if manifest_on_origin_only:
        sh(['checkout', '-q', '-b', branch, 'HEAD~1'], work)
    elif branch != 'main':
        sh(['checkout', '-q', '-b', branch], work)
    return work


def record_hash(work):
    h = hashlib.sha256()
    top = os.path.join(work, 'docs', 'artifacts')
    for d, _dirs, files in sorted(os.walk(top)):
        for name in sorted(files):
            p = os.path.join(d, name)
            h.update(os.path.relpath(p, top).encode())
            with open(p, 'rb') as f:
                h.update(f.read())
    return h.hexdigest()


def run_hook(script, stdin, work, env=None, timeout=60):
    """Run one hook; checks INV-4 around it. stdin is a dict (sent as JSON) or a raw string."""
    full = {k: v for k, v in os.environ.items() if not k.startswith('CLAUDE_ARTIFACTS_')}
    full.update(env or {})
    raw = stdin if isinstance(stdin, str) else json.dumps(stdin)
    before = record_hash(work)
    t0 = time.time()
    p = subprocess.run([sys.executable, script], cwd=work, input=raw.encode('utf-8'),
                       capture_output=True, env=full, timeout=timeout)
    elapsed = time.time() - t0
    INV4['runs'] += 1
    if record_hash(work) != before:
        INV4['violations'].append('%s changed docs/artifacts' % os.path.basename(script))
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace'), elapsed


def bash_input(work, command, error=None, interrupted=False, event=None):
    """Hook input for a Bash call: PostToolUse when it succeeded, PostToolUseFailure with `error`."""
    d = {'session_id': 's1', 'cwd': work, 'tool_name': 'Bash', 'tool_input': {'command': command}}
    if error is not None:
        d.update(hook_event_name='PostToolUseFailure', error=error, is_interrupt=interrupted)
    else:
        d.update(hook_event_name='PostToolUse',
                 tool_response={'stdout': 'ok', 'stderr': '', 'interrupted': interrupted, 'isImage': False})
    return d


def queue_of(work):
    data = read_json(os.path.join(work, '.claude', 'artifacts-queue.json'), {})
    return data.get('events', []) if isinstance(data, dict) else []


def after(work, command, error=None, env=None, **kw):
    return run_hook(AFTER, bash_input(work, command, error, **kw), work, env)


def statuses(work):
    return [(e['id'], e['suggested_status']) for e in queue_of(work)]


# --- after-command hook: the section 8.1 table ----------------------------------------

FAIL1 = 'Exit code 1\nsomething failed'
TABLE = [
    # (command, error or None, expected status)
    ('gh pr create --title "t" --body "b"', None, 'Running'),
    ('gh pr ready', None, 'Waiting'),
    ('gh pr merge 12 --squash', None, 'Live'),
    ('python scripts/delivery/ci_watch.py 12', FAIL1, 'Failed'),
    ('python scripts/delivery/ci_watch.py 12', None, 'Waiting'),
    ('gh run watch 99 --exit-status', FAIL1, 'Failed'),
    ('gh run watch 99', None, 'Waiting'),
    ('vercel deploy --prod', None, 'Live'),
    ('fly deploy', None, 'Live'),
    ('wrangler deploy', None, 'Live'),
    ('firebase deploy --only hosting', None, 'Live'),
]


def _row(command, error, status):
    def t():
        work = make_repo()
        rc, _out, err, _ = after(work, command, error)
        assert rc == 0, (rc, err)
        assert statuses(work) == [('AR5', status)], queue_of(work)
        ev = queue_of(work)[0]
        assert set(ev) >= {'id', 'suggested_status', 'event', 'command', 'time'}, ev
        # the same command on main or without a manifest queues nothing
        main_repo = make_repo(branch='main')
        assert after(main_repo, command, error)[0] == 0
        assert queue_of(main_repo) == [], 'queued on main'
        bare = make_repo(manifest=False)
        assert after(bare, command, error)[0] == 0
        assert queue_of(bare) == [], 'queued without a manifest'
    t.__name__ = 'after_command_row: %s [%s] -> %s' % (command, 'fail' if error else 'ok', status)
    return t


for _c, _e, _s in TABLE:
    test(_row(_c, _e, _s))


@test
def after_merged_status_built_from_manifest():
    work = make_repo(merged_status='Built')
    after(work, 'gh pr merge 3')
    assert statuses(work) == [('AR5', 'Built')], queue_of(work)
    old = make_repo(merged_status='Done')          # the retired name reads as Built (R6.9)
    after(old, 'gh pr merge 3')
    assert statuses(old) == [('AR5', 'Built')], queue_of(old)


@test
def after_failed_commands_queue_nothing_unless_watch_or_ci():
    work = make_repo()
    for cmd in ('gh pr create', 'gh pr ready', 'gh pr merge 3', 'vercel deploy --prod', 'fly deploy',
                'wrangler deploy', 'firebase deploy'):
        assert after(work, cmd, FAIL1)[0] == 0
    assert queue_of(work) == [], queue_of(work)


@test
def after_interrupted_queues_nothing():
    work = make_repo()
    after(work, 'gh run watch 1', 'Exit code 130\n', interrupted=True)
    after(work, 'gh pr create', interrupted=True)
    assert queue_of(work) == [], queue_of(work)


@test
def after_non_matching_and_quoted_text_queue_nothing():
    work = make_repo()
    for cmd in ('git status', 'echo hello', 'git commit -m "docs: how gh pr create works"',
                'gh pr view 3', 'gh pr merge 3 --auto', 'vercel deploy', 'npm test'):
        assert after(work, cmd)[0] == 0
    assert queue_of(work) == [], queue_of(work)


@test
def after_matches_inside_chains_wrappers_and_windows_paths():
    for cmd, status in (('cd sub && gh pr create --title "t"', 'Running'),
                        ('rtk gh pr ready', 'Waiting'),
                        ('CI=1 gh pr merge 3', 'Live'),
                        ('python3 .\\scripts\\delivery\\ci_watch.py 7', 'Waiting'),
                        ('git push && gh pr create --fill', 'Running')):
        work = make_repo()
        after(work, cmd)
        assert statuses(work) == [('AR5', status)], (cmd, queue_of(work))


@test
def after_same_event_is_queued_once():
    work = make_repo()
    after(work, 'gh pr ready')
    after(work, 'gh pr ready')
    assert len(queue_of(work)) == 1, queue_of(work)


@test
def after_task_id_follows_the_branch():
    work = make_repo(branch='DS12-agent-rules')
    after(work, 'gh pr ready')
    assert statuses(work) == [('DS12', 'Waiting')], queue_of(work)
    other = make_repo(branch='feature-without-an-id')
    after(other, 'gh pr ready')
    assert queue_of(other) == [], queue_of(other)


@test
def after_manifest_found_on_origin_default_branch():
    work = make_repo(manifest_on_origin_only=True)
    assert not os.path.exists(os.path.join(work, 'docs', 'artifacts', 'manifest.json'))
    after(work, 'gh pr ready')
    assert statuses(work) == [('AR5', 'Waiting')], queue_of(work)


@test
def after_errors_never_fail_garbage_stdin():
    work = make_repo()
    for raw in ('not json {', '', '[]', '"text"', '{"tool_input": null}', '{"tool_input": {"command": 5}}',
                '{"tool_name": "Bash"}', json.dumps({'cwd': os.path.join(work, 'nope'),
                                                     'tool_input': {'command': 'gh pr create'}})):
        rc, _out, _err, _ = run_hook(AFTER, raw, work)
        assert rc == 0, (raw, rc)


@test
def after_internal_error_exits_zero_with_one_line_on_stderr():
    work = make_repo()
    write(os.path.join(work, '.claude'), 'a file where the queue folder should be\n')
    rc, out, err, _ = after(work, 'gh pr create')
    assert rc == 0 and out == '', (rc, out)
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1 and 'luismc-artifacts' in lines[0], err


@test
def after_finishes_in_under_two_seconds():
    work = make_repo()
    best = min(after(work, 'gh pr ready')[3] for _ in range(3))
    assert best < 2.0, best


@test
def after_hooks_off_queues_nothing():
    work = make_repo()
    rc, out, _e, _ = after(work, 'gh pr create', env={'CLAUDE_ARTIFACTS_HOOKS': 'off'})
    assert rc == 0 and out == '' and queue_of(work) == []
    after(work, 'gh pr create', env={'CLAUDE_ARTIFACTS_HOOKS': 'on'})
    assert queue_of(work) != []


# --- after-command hook: background work (R8.8) ----------------------------------------

def tool_input_for(work, tool, session='s1', failed=False, **tool_input):
    d = {'session_id': session, 'cwd': work, 'tool_name': tool, 'tool_input': tool_input,
         'hook_event_name': 'PostToolUseFailure' if failed else 'PostToolUse'}
    if failed:
        d['error'] = 'Exit code 1\nboom'
    else:
        d['tool_response'] = {'stdout': 'ok', 'stderr': '', 'interrupted': False}
    return d


def marker(work, session='s1'):
    entry = stop_state(work).get(session)
    return entry.get('background') if isinstance(entry, dict) else None


def background(work, tool, **kw):
    session = kw.pop('session', 's1')
    return run_hook(AFTER, tool_input_for(work, tool, session, **kw), work)


@test
def after_background_agent_and_bash_mark_the_session():
    for tool, args in (('Agent', {'prompt': 'do it', 'subagent_type': 'general-purpose', 'run_in_background': True}),
                       ('Task', {'prompt': 'do it', 'run_in_background': True}),
                       ('Agent', {'run_in_background': True}),
                       ('Bash', {'command': 'sleep 600', 'run_in_background': True})):
        work = make_repo(branch='main')       # no task ID in the branch is needed
        rc, out, err, _ = background(work, tool, **args)
        assert rc == 0 and out == '', (tool, rc, out, err)
        m = marker(work)
        assert m and m['session_id'] == 's1' and m['started'], (tool, stop_state(work))
        assert queue_of(work) == [], 'the marker is not a queued status change'
    # another session has its own marker
    background(work, 'Agent', session='s2', run_in_background=True)
    assert marker(work, 's2') and marker(work, 's1')


@test
def after_foreground_calls_do_not_mark_the_session():
    """R8.8: only run_in_background true arms the check; a foreground Agent or Task finishes within the turn."""
    work = make_repo()
    for ti in ({'command': 'ls'}, {'command': 'ls', 'run_in_background': False},
               {'command': 'ls', 'run_in_background': 'true'}):
        assert after_raw(work, ti)[0] == 0
    assert stop_state(work) == {}, stop_state(work)
    for tool in ('Agent', 'Task'):
        for args in ({'prompt': 'do it'}, {}, {'prompt': 'x', 'run_in_background': False},
                     {'prompt': 'x', 'run_in_background': 'true'}, {'prompt': 'x', 'run_in_background': None},
                     {'prompt': 'x', 'run_in_background': 1}):
            rc, out, err, _ = background(work, tool, **args)
            assert rc == 0 and out == '' and stop_state(work) == {}, (tool, args, stop_state(work), err)
    other = tool_input_for(work, 'Read', file_path='x')       # tools the hook is not registered for
    assert run_hook(AFTER, other, work)[0] == 0 and stop_state(work) == {}
    # a launch that failed started nothing
    rc = background(work, 'Bash', failed=True, command='sleep 9', run_in_background=True)[0]
    assert rc == 0 and stop_state(work) == {}, stop_state(work)
    rc = background(work, 'Agent', failed=True, prompt='x', run_in_background=True)[0]
    assert rc == 0 and stop_state(work) == {}, stop_state(work)


def after_raw(work, tool_input):
    return run_hook(AFTER, tool_input_for(work, 'Bash', **tool_input), work)


@test
def after_background_marker_needs_a_manifest():
    work = make_repo(manifest=False)
    assert background(work, 'Agent', prompt='x', run_in_background=True)[0] == 0
    assert stop_state(work) == {} and not os.path.exists(os.path.join(work, '.claude')), 'wrote without a manifest'


@test
def after_background_bash_still_queues_its_status_event():
    work = make_repo()
    background(work, 'Bash', command='gh pr create --title t', run_in_background=True)
    assert statuses(work) == [('AR5', 'Running')] and marker(work), (queue_of(work), stop_state(work))


@test
def after_background_marker_survives_a_broken_state_file_and_hooks_off():
    work = make_repo()
    write(os.path.join(work, '.claude', 'artifacts-stop-state.json'), '{not json')
    assert background(work, 'Agent', prompt='x', run_in_background=True)[0] == 0 and marker(work)
    off = make_repo()
    run_hook(AFTER, tool_input_for(off, 'Agent', prompt='x', run_in_background=True), off,
             {'CLAUDE_ARTIFACTS_HOOKS': 'off'})
    assert stop_state(off) == {}


# --- end-of-turn hook -----------------------------------------------------------------

STUB_SCRIPT = '''import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "calls.log"), "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
mode = open(os.path.join(here, "mode")).read().strip() if os.path.exists(os.path.join(here, "mode")) else ""
if mode == "broken":
    sys.stderr.write("boom")
    sys.exit(2)
data = json.load(open(os.path.join(here, "pending.json")))
if data["artifacts"] or data["queue"]:
    print(json.dumps(data))
    sys.exit(1)
print(json.dumps(data))
sys.exit(0)
'''


def stub_dir(work):
    d = os.path.join(os.path.dirname(work), 'stubs')
    os.makedirs(d, exist_ok=True)
    write(os.path.join(d, 'project_artifacts.py'), STUB_SCRIPT)
    return d


def set_pending(work, artifacts=(), queue=(), mode=''):
    d = stub_dir(work)
    write(os.path.join(d, 'pending.json'), json.dumps({'artifacts': list(artifacts), 'queue': list(queue)}))
    write(os.path.join(d, 'mode'), mode)
    return {'CLAUDE_ARTIFACTS_SCRIPT': os.path.join(d, 'project_artifacts.py')}


def art(key, reason='html changed since the last publish'):
    """A `pending` entry for Full Progress (the only artifact pending lists, R9.5); `key` only tells two
    different pending sets apart."""
    return {'key': key, 'kind': 'full-progress', 'title': 'Full Progress: ' + key.title(),
            'file': 'full-progress-%s.html' % key, 'path': '/publish/copy/full-progress-%s.html' % key,
            'url': 'https://claude.ai/artifact/' + key, 'reason': reason}


def feature_entry(key='site'):
    """What an older script would still list: a feature artifact (R8.11 ignores it)."""
    return {'key': key, 'kind': 'feature', 'title': 'Feature: ' + key.title(), 'file': 'feature-%s.html' % key,
            'path': '/record/feature-%s.html' % key, 'url': '', 'reason': 'never published'}


def stop(work, env, session='s1', extra=None):
    d = {'session_id': session, 'cwd': work, 'hook_event_name': 'Stop', 'stop_hook_active': False}
    d.update(extra or {})
    return run_hook(STOP, d, work, env)


def stop_state(work):
    return read_json(os.path.join(work, '.claude', 'artifacts-stop-state.json'), {})


def parse_stop(out):
    return json.loads(out) if out.strip() else {}


@test
def stop_blocks_when_an_artifact_is_pending():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    rc, out, err, _ = stop(work, env)
    res = parse_stop(out)
    assert rc == 0 and res.get('decision') == 'block', (rc, out, err)
    r = res['reason']
    assert 'Full Progress: Demo' in r and 'mark-published demo' in r and 'full-progress-demo.html' in r, r
    assert 'https://claude.ai/artifact/demo' in r, r
    assert '/publish/copy/full-progress-demo.html' in r and 'once' in r and 'end of the turn' in r, r   # R3.1, R5.31
    assert 'never published' in r, r
    calls = open(os.path.join(os.path.dirname(work), 'stubs', 'calls.log')).read().split('\n')
    assert 'pending --json' in calls, calls


@test
def stop_counts_only_full_progress():
    """R8.11: a feature artifact in `pending` neither blocks the stop nor counts towards the give-up."""
    work = make_repo()
    env = set_pending(work, artifacts=[feature_entry('site'), feature_entry('other')])
    rc, out, err, _ = stop(work, env)
    assert rc == 0 and out.strip() == '' and stop_state(work) == {}, (rc, out, err, stop_state(work))
    # an entry with no kind and a key that is not full-progress is a feature too
    legacy = {'key': 'site', 'title': 'Feature: Site', 'file': 'feature-site.html', 'url': '', 'reason': 'x'}
    env = set_pending(work, artifacts=[legacy])
    assert stop(work, env)[1].strip() == ''
    # beside Full Progress it is left out of the reason, the fingerprint and the count
    env = set_pending(work, artifacts=[feature_entry('site'), art('demo')])
    res = parse_stop(stop(work, env)[1])
    assert res['decision'] == 'block' and 'Full Progress: Demo' in res['reason'], res
    assert 'Feature: Site' not in res['reason'] and 'feature-site.html' not in res['reason'], res['reason']
    first = stop_state(work)['s1']['last']
    set_pending(work, artifacts=[art('demo')])
    stop(work, env)
    assert stop_state(work)['s1']['last'] == first and stop_state(work)['s1']['blocks'] == 2, stop_state(work)
    # a feature artifact appearing later does not restart the count
    set_pending(work, artifacts=[feature_entry('late'), art('demo')])
    stop(work, env)
    assert stop_state(work)['s1']['blocks'] == 3
    res = parse_stop(stop(work, env)[1])
    assert 'decision' not in res and 'Full Progress: Demo' in res['systemMessage'], res
    assert 'Feature' not in res['systemMessage'], res


@test
def stop_blocks_on_events_reported_by_pending():
    work = make_repo()
    env = set_pending(work, queue=[{'id': 'AR5', 'suggested_status': 'Waiting', 'event': 'gh pr ready'}])
    res = parse_stop(stop(work, env)[1])
    assert res.get('decision') == 'block', res
    assert 'AR5' in res['reason'] and 'set-task-status AR5 "Waiting"' in res['reason'], res['reason']


@test
def stop_blocks_on_the_queue_file_even_when_pending_is_empty():
    work = make_repo()
    env = set_pending(work)
    after(work, 'gh pr ready')
    res = parse_stop(stop(work, env)[1])
    assert res.get('decision') == 'block' and 'AR5' in res['reason'], res


@test
def stop_passes_with_nothing_pending():
    work = make_repo()
    env = set_pending(work)
    rc, out, _e, _ = stop(work, env)
    assert rc == 0 and out.strip() == '', (rc, out)


@test
def stop_does_nothing_without_a_manifest():
    work = make_repo(manifest=False)
    env = set_pending(work, artifacts=[art('demo')])
    rc, out, _e, _ = stop(work, env)
    assert rc == 0 and out.strip() == '', (rc, out)
    assert not os.path.exists(os.path.join(os.path.dirname(work), 'stubs', 'calls.log'))


@test
def stop_hooks_off_does_nothing():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    env['CLAUDE_ARTIFACTS_HOOKS'] = 'off'
    rc, out, _e, _ = stop(work, env)
    assert rc == 0 and out.strip() == '', (rc, out)
    assert stop_state(work) == {}


@test
def stop_lets_go_after_three_unchanged_blocks_with_a_system_message():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    for n in (1, 2, 3):
        res = parse_stop(stop(work, env)[1])
        assert res.get('decision') == 'block', (n, res)
        assert stop_state(work)['s1']['blocks'] == n, stop_state(work)
    rc, out, _e, _ = stop(work, env)
    res = parse_stop(out)
    assert rc == 0 and 'decision' not in res, res
    assert 'Full Progress: Demo' in res['systemMessage'] and 'full-progress-demo.html' in res['systemMessage'], res
    assert 'decision' not in parse_stop(stop(work, env)[1])   # stays open while unchanged


@test
def stop_block_count_resets_when_what_is_pending_changes():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    stop(work, env)
    stop(work, env)
    assert stop_state(work)['s1']['blocks'] == 2
    set_pending(work, artifacts=[art('other')])
    assert parse_stop(stop(work, env)[1]).get('decision') == 'block'
    assert stop_state(work)['s1']['blocks'] == 1, stop_state(work)
    stop(work, env)
    assert parse_stop(stop(work, env)[1]).get('decision') == 'block'      # third block of the new set
    assert 'decision' not in parse_stop(stop(work, env)[1])               # fourth lets go


@test
def stop_block_count_resets_when_nothing_is_pending():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    stop(work, env)
    stop(work, env)
    set_pending(work)
    assert stop(work, env)[1].strip() == ''
    assert 's1' not in stop_state(work), stop_state(work)
    set_pending(work, artifacts=[art('demo')])
    stop(work, env)
    assert stop_state(work)['s1']['blocks'] == 1


@test
def stop_counts_each_session_separately():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    for _ in range(3):
        stop(work, env, session='a')
    assert 'decision' not in parse_stop(stop(work, env, session='a')[1])
    assert parse_stop(stop(work, env, session='b')[1]).get('decision') == 'block'


@test
def stop_fails_open_when_pending_cannot_be_read():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')], mode='broken')
    rc, out, err, _ = stop(work, env)
    assert rc == 0 and out.strip() == '' and 'pending failed (exit 2)' in err, (rc, out, err)
    env2 = {'CLAUDE_ARTIFACTS_SCRIPT': os.path.join(work, 'missing.py')}
    rc, out, err, _ = stop(work, env2)
    assert rc == 0 and out.strip() == '', (rc, out)
    # ... but a queued event in the queue file still blocks
    after(work, 'gh pr ready')
    res = parse_stop(stop(work, env)[1])
    assert res.get('decision') == 'block' and 'set-task-status AR5' in res['reason'], res


@test
def stop_garbage_stdin_exits_zero():
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    for raw in ('garbage', '', '[]', '{"session_id": 5}'):
        assert run_hook(STOP, raw, work, env)[0] == 0, raw


# --- end-of-turn hook: background work (R8.10) -----------------------------------------

NO_ACTIVE = ['Live', 'Built', 'To do', 'On hold', 'Failed']
BG_REASON = 'started in the background'


def bg_started(work, session='s1'):
    assert background(work, 'Agent', prompt='x', session=session, run_in_background=True)[0] == 0


@test
def stop_blocks_background_work_without_an_active_task():
    work = make_repo(statuses=NO_ACTIVE)
    env = set_pending(work)
    assert stop(work, env)[1].strip() == ''          # nothing started: nothing asked
    bg_started(work)
    rc, out, err, _ = stop(work, env)
    res = parse_stop(out)
    assert rc == 0 and res.get('decision') == 'block', (rc, out, err)
    r = res['reason']
    assert BG_REASON in r and 'no task is Running' in r and 'task-add' in r and 'set-task-status' in r, r
    assert marker(work), 'the marker stays until a task is Running'
    assert stop_state(work)['s1']['blocks'] == 1
    assert parse_stop(stop(work, env)[1]).get('decision') == 'block'     # still no task: blocks again


@test
def stop_background_blocks_for_background_bash_and_task_calls_too():
    """... and a foreground sub-agent, however many, asks for nothing."""
    quiet = make_repo(statuses=NO_ACTIVE)
    for tool in ('Agent', 'Task'):
        assert background(quiet, tool, prompt='x')[0] == 0
    assert stop(quiet, set_pending(quiet))[1].strip() == ''
    assert stop_state(quiet) == {}
    for tool, args in (('Task', {'prompt': 'x', 'run_in_background': True}),
                       ('Bash', {'command': 'x', 'run_in_background': True})):
        work = make_repo(statuses=NO_ACTIVE)
        env = set_pending(work)
        assert background(work, tool, **args)[0] == 0
        assert parse_stop(stop(work, env)[1]).get('decision') == 'block', tool


@test
def stop_allows_background_work_with_an_active_task_and_clears_the_marker():
    for status in ('Running', 'Waiting', 'Needs you'):
        work = make_repo(statuses=['Built', status])
        env = set_pending(work)
        bg_started(work)
        rc, out, err, _ = stop(work, env)
        assert rc == 0 and out.strip() == '', (status, rc, out, err)
        assert 's1' not in stop_state(work), (status, stop_state(work))
        # armed again by the next background launch
        bg_started(work)
        assert marker(work)


@test
def stop_background_clears_once_a_task_becomes_running_in_the_record_worktree():
    work = make_repo(statuses=NO_ACTIVE)
    env = set_pending(work)
    bg_started(work)
    assert parse_stop(stop(work, env)[1]).get('decision') == 'block'
    # the session records the task: the script commits to the record worktree (freshest source)
    record = os.path.join(work, '.claude', 'worktrees', 'artifacts-record', 'docs', 'artifacts', 'registry.json')
    write(record, json.dumps({'spec': 'ARTIFACTSPEC 1.0.0', 'tasks': [
        {'id': 'AR30', 'owner': 'project', 'status': 'Running', 'item': 'y'}]}))
    rc, out, _e, _ = stop(work, env)
    assert rc == 0 and out.strip() == '' and 's1' not in stop_state(work), (out, stop_state(work))
    # ... and a stale Running task in the session checkout does not count over a fresher source
    stale = make_repo(statuses=['Running'])
    write(os.path.join(stale, '.claude', 'worktrees', 'artifacts-record', 'docs', 'artifacts', 'registry.json'),
          json.dumps({'spec': 'ARTIFACTSPEC 1.0.0', 'tasks': [{'id': 'AR5', 'owner': 'project',
                                                              'status': 'Built', 'item': 'x'}]}))
    bg_started(stale)
    assert parse_stop(stop(stale, set_pending(stale))[1]).get('decision') == 'block'


@test
def stop_background_gives_up_after_three_blocks():
    work = make_repo(statuses=NO_ACTIVE)
    env = set_pending(work)
    bg_started(work)
    for n in (1, 2, 3):
        res = parse_stop(stop(work, env)[1])
        assert res.get('decision') == 'block', (n, res)
        assert stop_state(work)['s1']['blocks'] == n, stop_state(work)
    rc, out, _e, _ = stop(work, env)
    res = parse_stop(out)
    assert rc == 0 and 'decision' not in res and BG_REASON in res['systemMessage'], res


@test
def stop_background_shares_the_give_up_rule_with_pending_artifacts():
    work = make_repo(statuses=NO_ACTIVE)
    env = set_pending(work, artifacts=[art('demo')])
    bg_started(work)
    res = parse_stop(stop(work, env)[1])
    assert res['decision'] == 'block' and 'Full Progress: Demo' in res['reason'] and BG_REASON in res['reason'], res
    stop(work, env)
    stop(work, env)
    res = parse_stop(stop(work, env)[1])
    assert 'decision' not in res and 'Full Progress: Demo' in res['systemMessage'] and BG_REASON in res['systemMessage'], res
    # the artifact gets published: what is pending changed, so the count restarts
    env = set_pending(work)
    assert parse_stop(stop(work, env)[1]).get('decision') == 'block'
    assert stop_state(work)['s1']['blocks'] == 1


@test
def stop_background_is_per_session():
    work = make_repo(statuses=NO_ACTIVE)
    env = set_pending(work)
    bg_started(work, 'a')
    assert parse_stop(stop(work, env, session='a')[1]).get('decision') == 'block'
    assert stop(work, env, session='b')[1].strip() == ''


@test
def stop_background_is_a_no_op_without_a_manifest_or_when_off():
    work = make_repo(manifest=False)
    write(os.path.join(work, '.claude', 'artifacts-stop-state.json'),
          json.dumps({'s1': {'background': {'started': 'now', 'session_id': 's1'}}}))
    env = set_pending(work)
    rc, out, _e, _ = stop(work, env)
    assert rc == 0 and out.strip() == '', (rc, out)
    off = make_repo(statuses=NO_ACTIVE)
    bg_started(off)
    env = set_pending(off)
    env['CLAUDE_ARTIFACTS_HOOKS'] = 'off'
    assert stop(off, env)[1].strip() == ''


@test
def stop_background_fails_open_when_the_registry_cannot_be_read():
    work = make_repo(statuses=NO_ACTIVE)
    bg_started(work)
    # no registry in any source: the check cannot tell, so the turn may end
    sh(['rm', '-q', '-f', 'docs/artifacts/registry.json'], work)
    sh(['commit', '-q', '-m', 'drop registry'], work)
    sh(['push', '-q', 'origin', 'HEAD:main'], work)
    rc, out, err, _ = stop(work, set_pending(work))
    assert rc == 0 and out.strip() == '', (rc, out, err)


# --- session-start hook ---------------------------------------------------------------

GH_STUB = '''import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "gh.log"), "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
if os.path.exists(os.path.join(here, "gh_fail")):
    sys.stderr.write("gh: not logged in")
    sys.exit(4)
sys.stdout.write(open(os.path.join(here, "prs.json")).read())
'''

PRS = [
    {'headRefName': 'AR5-first', 'state': 'MERGED', 'mergedAt': '2026-10-09T10:00:00Z'},
    {'headRefName': 'AR6-second', 'state': 'MERGED', 'mergedAt': '2026-10-09T10:00:00Z'},
    {'headRefName': 'AR7-third', 'state': 'MERGED', 'mergedAt': '2026-10-09T10:00:00Z'},
    {'headRefName': 'AR8-needs-you', 'state': 'MERGED', 'mergedAt': '2026-10-09T10:00:00Z'},
    {'headRefName': 'AR9-abandoned', 'state': 'CLOSED', 'mergedAt': None},
    {'headRefName': 'AR10-in-review', 'state': 'OPEN', 'mergedAt': None},
    {'headRefName': 'AR11-shipped', 'state': 'MERGED', 'mergedAt': '2026-10-09T10:00:00Z'},
    {'headRefName': 'AR12-no-task', 'state': 'MERGED', 'mergedAt': '2026-10-09T10:00:00Z'},
    {'headRefName': 'feature/plain', 'state': 'MERGED', 'mergedAt': '2026-10-09T10:00:00Z'},
    {'headRefName': 'AR13-retry', 'state': 'CLOSED', 'mergedAt': None},
    {'headRefName': 'AR13-retry-2', 'state': 'MERGED', 'mergedAt': '2026-10-09T11:00:00Z'},
]


def gh_env(work, prs=PRS, fail=False):
    d = os.path.join(os.path.dirname(work), 'ghstub')
    os.makedirs(d, exist_ok=True)
    write(os.path.join(d, 'gh.py'), GH_STUB)
    write(os.path.join(d, 'prs.json'), json.dumps(prs))
    flag = os.path.join(d, 'gh_fail')
    if fail:
        write(flag, '1')
    elif os.path.exists(flag):
        os.remove(flag)
    return {'CLAUDE_ARTIFACTS_GH': os.path.join(d, 'gh.py')}


def start(work, env, raw=None):
    return run_hook(START, raw if raw is not None else
                    {'session_id': 's1', 'cwd': work, 'hook_event_name': 'SessionStart', 'source': 'startup'},
                    work, env)


@test
def start_queues_merged_closed_and_ignores_the_rest():
    work = make_repo(branch='main')
    rc, out, err, _ = start(work, gh_env(work))
    assert rc == 0, err
    got = sorted(statuses(work))
    assert got == sorted([('AR5', 'Live'), ('AR6', 'Live'), ('AR7', 'Live'), ('AR9', 'On hold'),
                          ('AR13', 'Live')]), got
    # AR8 (Needs you), AR10 (open PR), AR11 (already Live), AR12 (no task), feature/plain: nothing
    res = json.loads(out)
    assert sorted(res) == ['hookSpecificOutput', 'systemMessage'], res
    for frag in ('AR5 -> Live', 'AR9 -> On hold'):
        assert frag in res['systemMessage'], res
    args = open(os.path.join(os.path.dirname(work), 'ghstub', 'gh.log')).read().split('\n')
    assert 'pr list --state all --json headRefName,state,mergedAt --limit 200' in args, args


@test
def start_uses_merged_status_built_from_manifest():
    work = make_repo(branch='main', merged_status='Built')
    start(work, gh_env(work))
    got = dict(statuses(work))
    assert got['AR5'] == 'Built' and got['AR9'] == 'On hold', got


@test
def start_does_not_queue_twice():
    work = make_repo(branch='main')
    env = gh_env(work)
    start(work, env)
    n = len(queue_of(work))
    start(work, env)
    assert len(queue_of(work)) == n > 0


@test
def start_skips_with_one_system_message_when_gh_fails():
    work = make_repo(branch='main')
    rc, out, err, _ = start(work, gh_env(work, fail=True))
    assert rc == 0 and queue_of(work) == [], (rc, queue_of(work))
    res = json.loads(out)
    assert sorted(res) == ['hookSpecificOutput', 'systemMessage'] and 'skipped' in res['systemMessage'], res
    assert out.strip().count('\n') == 0   # one message, one line
    assert 'exit 4' in res['systemMessage'], res


@test
def start_skips_when_gh_is_missing():
    work = make_repo(branch='main')
    rc, out, _e, _ = start(work, {'CLAUDE_ARTIFACTS_GH': os.path.join(work, 'no-such-gh-binary')})
    res = json.loads(out)
    assert rc == 0 and queue_of(work) == [] and 'skipped' in res['systemMessage'], (rc, out)


@test
def start_lists_events_already_queued():
    work = make_repo(branch='AR5-x')
    after(work, 'gh pr ready')
    rc, out, _e, _ = start(work, gh_env(work, prs=[]))
    res = json.loads(out)
    assert 'AR5 -> Waiting' in res['systemMessage'], res


@test
def start_prints_only_the_rule_with_nothing_to_report():
    work = make_repo(branch='main')
    rc, out, _e, _ = start(work, gh_env(work, prs=[]))
    assert rc == 0 and list(json.loads(out)) == ['hookSpecificOutput'], (rc, out)


@test
def start_does_nothing_without_a_manifest():
    work = make_repo(manifest=False, branch='main')
    rc, out, _e, _ = start(work, gh_env(work))
    assert rc == 0 and out.strip() == '' and queue_of(work) == [], (rc, out)
    assert not os.path.exists(os.path.join(os.path.dirname(work), 'ghstub', 'gh.log'))


@test
def start_hooks_off_does_nothing():
    work = make_repo(branch='main')
    env = gh_env(work)
    env['CLAUDE_ARTIFACTS_HOOKS'] = 'off'
    rc, out, _e, _ = start(work, env)
    assert rc == 0 and out.strip() == '' and queue_of(work) == []
    assert not os.path.exists(os.path.join(os.path.dirname(work), 'ghstub', 'gh.log'))


@test
def start_garbage_stdin_exits_zero():
    work = make_repo(branch='main')
    for raw in ('garbage', '', '[]'):
        assert start(work, gh_env(work, prs=[]), raw=raw)[0] == 0, raw


@test
def start_delivers_the_rule_as_additional_context():
    rule = open(os.path.join(PLUGIN, 'rules', 'project-artifacts.md'), encoding='utf-8').read().strip()
    work = make_repo(branch='main')
    rc, out, err, _ = start(work, gh_env(work, prs=[]))
    res = json.loads(out)
    assert rc == 0 and out.strip().count('\n') == 0, (rc, out, err)
    hso = res['hookSpecificOutput']
    assert hso['hookEventName'] == 'SessionStart' and rule in hso['additionalContext'], hso
    # with a system message too, still in one document
    res = json.loads(start(make_repo(branch='main'), gh_env(work))[1])
    assert 'AR5 -> Live' in res['systemMessage'] and rule in res['hookSpecificOutput']['additionalContext'], res
    # every session: a second start prints it again
    assert rule in json.loads(start(work, gh_env(work, prs=[]))[1])['hookSpecificOutput']['additionalContext']


@test
def start_delivers_the_rule_when_gh_is_missing():
    rule = open(os.path.join(PLUGIN, 'rules', 'project-artifacts.md'), encoding='utf-8').read().strip()
    work = make_repo(branch='main')
    for env in ({'CLAUDE_ARTIFACTS_GH': os.path.join(work, 'no-such-gh-binary')}, gh_env(work, fail=True)):
        rc, out, _e, _ = start(work, env)
        res = json.loads(out)
        assert rc == 0 and 'skipped' in res['systemMessage'], out
        assert rule in res['hookSpecificOutput']['additionalContext'], out


@test
def start_delivers_the_rule_even_when_the_catch_up_breaks():
    rule = open(os.path.join(PLUGIN, 'rules', 'project-artifacts.md'), encoding='utf-8').read().strip()
    work = make_repo(branch='main')
    write(os.path.join(work, '.claude', 'artifacts-queue.json'), '{"events": 5}')
    rc, out, _e, _ = start(work, gh_env(work, prs=[{'headRefName': 'AR5-x', 'state': 'MERGED'}]))
    assert rc == 0 and rule in json.loads(out)['hookSpecificOutput']['additionalContext'], out


@test
def start_delivers_the_rule_on_a_task_branch_with_the_manifest_only_on_origin():
    rule = open(os.path.join(PLUGIN, 'rules', 'project-artifacts.md'), encoding='utf-8').read().strip()
    work = make_repo(manifest_on_origin_only=True)
    rc, out, _e, _ = start(work, gh_env(work, prs=[]))
    assert rc == 0 and rule in json.loads(out)['hookSpecificOutput']['additionalContext'], out


@test
def start_delivers_no_rule_without_a_manifest():
    work = make_repo(manifest=False, branch='main')
    rc, out, _e, _ = start(work, gh_env(work, prs=[]))
    assert rc == 0 and out.strip() == '', (rc, out)


@test
def rule_file_carries_the_activity_rules():
    """R3.2 to R3.5, R10.3: each of the four lines is in the plugin's rule file."""
    lines = [ln[2:] for ln in open(os.path.join(PLUGIN, 'rules', 'project-artifacts.md'),
                                   encoding='utf-8').read().splitlines() if ln.startswith('- ')]
    for old in ('Record work as a task before starting it.', 'Start branch names with the task ID.',
                'Change status only with `set-task-status`.',
                'Never type a status row by hand.', 'Put every doc under `docs/`.'):
        assert old in lines, old
    assert 'Publish what `pending` lists in the same turn.' not in lines        # R3.1: not after every change
    publish = [ln for ln in lines if ln.startswith('Publish Full Progress')]
    assert len(publish) == 1 and 'once, at the end of the turn, never mid-turn' in publish[0], publish
    assert 'feature artifacts are files in the repo' in publish[0] and 'never published' in publish[0], publish
    joined = '\n'.join(lines)
    for frag in ('Every activity is a task before it starts, whoever does it',
                 "the session's own", 'contracts', 'joins', 'test runs', 'releases', 'deploys', 'cleanup',
                 'A task is Running while any work for it runs',
                 'Waiting or Needs you when blocked on something or someone',
                 'Built means the work is finished but not released', 'release work still to come',
                 'is its own task, Running or To do',
                 'Before ending a turn that leaves work running in the background, its task is Running'):
        assert frag in joined, frag
    assert all(len(ln) < 260 for ln in lines), 'one short imperative line per rule'


# --- registration and invariants ------------------------------------------------------

@test
def hooks_json_registers_the_three_hooks():
    cfg = read_json(os.path.join(PLUGIN, 'hooks', 'hooks.json'))
    assert cfg and isinstance(cfg.get('hooks'), dict), cfg
    want = {'PostToolUse': 'hook_after_command.py', 'PostToolUseFailure': 'hook_after_command.py',
            'Stop': 'hook_end_of_turn.py', 'SessionStart': 'hook_session_start.py'}
    for event, script in want.items():
        groups = cfg['hooks'].get(event)
        assert groups, event
        cmds = [h['command'] for g in groups for h in g['hooks'] if h.get('type') == 'command']
        assert cmds and all('${CLAUDE_PLUGIN_ROOT}/scripts/' + script in c for c in cmds), (event, cmds)
        assert all(c.startswith('python3 ') and ' || python ' in c for c in cmds), cmds
        assert os.path.isfile(os.path.join(SCRIPTS, script)), script
    # R8.8: Agent and Task start background work, so PostToolUse also covers them
    assert [g.get('matcher') for g in cfg['hooks']['PostToolUse']] == ['Bash|Agent|Task']
    assert [g.get('matcher') for g in cfg['hooks']['PostToolUseFailure']] == ['Bash']


@test
def hooks_never_write_record():
    """INV-4: docs/artifacts/ is byte-identical around every hook run above (and these)."""
    work = make_repo()
    env = set_pending(work, artifacts=[art('demo')])
    env.update(gh_env(work))
    after(work, 'gh pr ready')
    background(work, 'Agent', prompt='x', run_in_background=True)
    stop(work, env)
    start(work, env)
    assert INV4['runs'] > 40, INV4['runs']
    assert INV4['violations'] == [], INV4['violations']


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
    cleanup()
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
