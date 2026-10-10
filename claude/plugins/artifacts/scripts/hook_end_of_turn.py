#!/usr/bin/env python3
"""End-of-turn hook (Stop).

ARTIFACTSPEC 1.1.0 section 8.2. Lets the turn end only when the queue is empty and
`project_artifacts.py pending` lists nothing; otherwise blocks the stop with
{"decision": "block", "reason": ...} naming each item and the commands to run
(R8.3). It also blocks when this session started background work (marked by
hook_after_command, R8.8) and the registry has no task in Running, Waiting or
Needs you (R8.10); once such a task exists the marker is cleared. After 3
consecutive blocks in one session with no change in what is pending it lets the
turn end and prints a systemMessage instead (R8.4), so a session that cannot
publish never loops. It only reads the record (INV-4).

Per-session state: <repo>/.claude/artifacts-stop-state.json, shaped
{session_id: {"blocks": n, "last": <hash of what was pending>,
"background": {"started": <time>, ...}}}.

Seam for tests: CLAUDE_ARTIFACTS_SCRIPT overrides the path of project_artifacts.py.
Disable: CLAUDE_ARTIFACTS_HOOKS=off. Standard library only.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hook_after_command import (STATE_NAME, command_for, hook_root, hooks_off,  # noqa: E402
                                load_manifest, origin_record_file, parse_json, read_input,
                                read_state, run, warn, write_state)

BLOCK_LIMIT = 3          # R8.4; the ceiling in section 12 is 5, it may only be lowered
PENDING_TIMEOUT = 90
ACTIVE_STATUSES = ('Running', 'Waiting', 'Needs you')   # R8.10
BACKGROUND_NOTE = 'work started in the background with no Running task'


def script_path():
    return os.environ.get('CLAUDE_ARTIFACTS_SCRIPT') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'project_artifacts.py')


def pending_items(root, script):
    """(artifacts, queue) from `pending --json`; None when it cannot be read."""
    r = run(command_for(script) + ['pending', '--json'], root, PENDING_TIMEOUT)
    if r is None:
        warn('pending could not run (%s)' % script)
        return None
    rc, out, err = r
    if rc == 0:
        return [], []
    if rc != 1:
        warn('pending failed (exit %d)' % rc)
        return None
    try:
        data = json.loads(out)
        artifacts = [a for a in data.get('artifacts', []) if isinstance(a, dict)]
        queue = [e for e in data.get('queue', []) if isinstance(e, dict)]
    except (ValueError, AttributeError):
        warn('pending printed output that is not JSON (exit 1)')
        return None
    return artifacts, queue


def merge_queue(root, queue):
    """The queue pending reported plus the queue file, without duplicates."""
    from artifact_queue import read_queue
    merged = list(queue)
    seen = {(e.get('id'), e.get('suggested_status'), e.get('event')) for e in merged}
    for e in read_queue(root):
        k = (e.get('id'), e.get('suggested_status'), e.get('event'))
        if isinstance(e, dict) and k not in seen:
            seen.add(k)
            merged.append(e)
    return merged


def registry_tasks(root, manifest):
    """The task list from the freshest registry: the record worktree, else origin/<branch>, else
    the checkout. None when none can be read."""
    branch = manifest.get('default_branch') if isinstance(manifest.get('default_branch'), str) else 'main'
    rel = os.path.join('docs', 'artifacts', 'registry.json')
    sources = [os.path.join(root, '.claude', 'worktrees', 'artifacts-record', rel), 'origin',
               os.path.join(root, rel)]
    for source in sources:
        if source == 'origin':
            text = origin_record_file(root, branch, 'registry.json')
        else:
            try:
                with open(source, encoding='utf-8') as f:
                    text = f.read()
            except OSError:
                continue
        registry = parse_json(text, 'registry.json') if text is not None else None
        if registry is not None and isinstance(registry.get('tasks'), list):
            return [t for t in registry['tasks'] if isinstance(t, dict)]
    return None


def has_active_task(root, manifest):
    """True when a task is Running, Waiting or Needs you. An unreadable registry counts as yes
    (fail open)."""
    tasks = registry_tasks(root, manifest)
    if tasks is None:
        warn('registry.json unreadable; background-work check skipped')
        return True
    return any(t.get('status') in ACTIVE_STATUSES for t in tasks)


def fingerprint(artifacts, queue, background=False):
    """Stable hash of what is pending (keys and queued changes, not wording)."""
    parts = sorted([['artifact', str(a.get('key'))] for a in artifacts]
                   + [['event', str(e.get('id')), str(e.get('suggested_status'))] for e in queue]
                   + ([['background']] if background else []))
    return hashlib.sha256(json.dumps(parts).encode('utf-8')).hexdigest()[:16]


def describe(artifacts, queue, background=False):
    """One line per pending item, for the systemMessage."""
    lines = ['%s (%s)' % (a.get('title') or a.get('key'), a.get('file', '')) for a in artifacts]
    lines += ['%s -> %s' % (e.get('id'), e.get('suggested_status')) for e in queue]
    if background:
        lines.append(BACKGROUND_NOTE)
    return '; '.join(lines)


def build_reason(root, script, artifacts, queue):
    py = 'python "%s"' % script
    record = os.path.join(root, '.claude', 'worktrees', 'artifacts-record', 'docs', 'artifacts')
    out = ['Project artifacts are not up to date. Finish this in the same turn:']
    for e in queue:
        i = e.get('id')
        out.append('- Queued status change %s -> %s (%s). If it is true, run: %s set-task-status %s "%s". '
                   'If not, drop it: %s queue clear --id %s'
                   % (i, e.get('suggested_status'), e.get('event', ''), py, i,
                      e.get('suggested_status'), py, i))
    for a in artifacts:
        key = a.get('key')
        target = ('update the existing artifact at %s' % a['url']) if a.get('url') else \
            'create it (first publish; after the Artifact tool is called, list the owner\'s artifacts first if the title may exist)'
        out.append('- Publish "%s" (%s; %s): read %s, publish it with the Artifact tool (%s), then run: '
                   '%s mark-published %s --url <the artifact URL>'
                   % (a.get('title') or key, a.get('file', ''), a.get('reason', 'pending'),
                      os.path.join(record, str(a.get('file', ''))), target, py, key))
    out.append('Then run %s pending --json to confirm nothing is left.' % py)
    return '\n'.join(out)


def build_background_reason(script):
    py = 'python "%s"' % script
    return ('Work was started in the background this turn but no task is Running. Record it with task-add '
            '(%s task-add --owner <key|project> --item ... --detail ... --expected ... --status Running) or '
            'set the task that covers it Running (%s set-task-status <ID> Running), then publish what '
            'pending lists. If the work is already finished, there is nothing to record: set its task '
            'Done only when nothing is left to do for it.' % (py, py))


def main():
    if hooks_off():
        return 0
    data = read_input()
    root = hook_root(data)
    if not root:
        return 0
    manifest = load_manifest(root)
    if manifest is None:
        return 0
    script = script_path()
    found = pending_items(root, script)
    # pending unreadable: fail open on artifacts, but the queue file is still a fact
    artifacts, queue = found if found is not None else ([], [])
    queue = merge_queue(root, queue)
    state_path = os.path.join(root, STATE_NAME)
    sid = str(data.get('session_id') or 'default')
    state = read_state(state_path)
    entry = state.get(sid) if isinstance(state.get(sid), dict) else {}
    marker = entry.get('background') if isinstance(entry.get('background'), dict) else None
    background = False
    if marker is not None:
        if has_active_task(root, manifest):
            marker = None     # a task is Running, Waiting or Needs you: the check is satisfied (R8.10)
            entry.pop('background', None)
            if not entry:
                state.pop(sid, None)
            else:
                state[sid] = entry
            write_state(state_path, state)
        else:
            background = True
    if not artifacts and not queue and not background:
        if sid in state:
            del state[sid]
            write_state(state_path, state)
        return 0
    digest = fingerprint(artifacts, queue, background)
    blocks = entry.get('blocks', 0) if entry.get('last') == digest else 0
    if not isinstance(blocks, int):
        blocks = 0
    if blocks >= BLOCK_LIMIT:
        print(json.dumps({'systemMessage': (
            'luismc-artifacts: letting the turn end after %d blocks with no change. Still unpublished, '
            'unapplied or unrecorded: %s. Run `pending` in the next session.'
            % (BLOCK_LIMIT, describe(artifacts, queue, background)))}))
        return 0
    state.pop(sid, None)   # keeps the most recently used session last
    new = {'blocks': blocks + 1, 'last': digest}
    if background:
        new['background'] = marker
    state[sid] = new
    write_state(state_path, state)
    parts = []
    if artifacts or queue:
        parts.append(build_reason(root, script, artifacts, queue))
    if background:
        parts.append(build_background_reason(script))
    print(json.dumps({'decision': 'block', 'reason': '\n\n'.join(parts)}))
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # fail open: a broken hook must not trap the session
        warn('end-of-turn hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
