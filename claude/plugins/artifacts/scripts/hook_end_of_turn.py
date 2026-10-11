#!/usr/bin/env python3
"""End-of-turn hook (Stop).

ARTIFACTSPEC 1.3.1 section 8.2. Lets the turn end only when the queue is empty and
`project_artifacts.py pending` lists nothing; otherwise blocks the stop with
{"decision": "block", "reason": ...} naming each item and the commands to run
(R8.3). It acts on Full Progress only, the one published artifact: a pending entry
for a feature artifact is ignored (R8.11). It also blocks when this session started background work (marked by
hook_after_command, R8.8) and the registry has no task in Running, Waiting or
Needs you (R8.10); once such a task exists the marker is cleared. After 3
consecutive blocks in one session with no change in what is pending it lets the
turn end and prints a systemMessage instead (R8.4), so a session that cannot
publish never loops. Before it decides it pushes the record commits that writing commands left unpushed
(`project_artifacts.py push`, R8.17); a failed push never blocks the turn, it adds a
systemMessage saying the commits stay local. Otherwise it only reads the record (INV-4).

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
                                load_manifest, migration_reasons_now, origin_record_file,
                                parse_json, read_input, read_state, run, script_path, warn,
                                worktree_dir, write_state)

BLOCK_LIMIT = 3          # R8.4; the ceiling in section 12 is 5, it may only be lowered
PENDING_TIMEOUT = 90
PUSH_TIMEOUT = 40
ACTIVE_STATUSES = ('Running', 'Waiting', 'Needs you')   # R8.10
BACKGROUND_NOTE = 'work started in the background with no Running task'
MIGRATION_NOTE = 'the artifact record needs migrating (run render)'


def push_record(root, script):
    """R8.17: push the unpushed record commits. '' when pushed or nothing to push, else the message to show."""
    r = run(command_for(script) + ['push'], root, PUSH_TIMEOUT)
    if r is None:
        warn('push could not run (%s)' % script)
        return 'luismc-artifacts: the record push could not run; the record commits stay local.'
    if r[0] == 0:
        return ''
    detail = (r[2] or r[1]).strip().splitlines()
    warn('push failed (exit %d)' % r[0])
    return ('luismc-artifacts: the record push failed (exit %d%s); the record commits stay local and the next '
            'push (end of the next turn, pending, or before gh pr create, ready or merge) tries again.'
            % (r[0], ': ' + detail[-1][:200] if detail else ''))


def pending_items(root, script):
    """(artifacts, queue, retired) from `pending --json`; None when it cannot be read. Retired pages never
    change pending's exit code, so they are read from its output at exit 0 as well (R8.13)."""
    r = run(command_for(script) + ['pending', '--json'], root, PENDING_TIMEOUT)
    if r is None:
        warn('pending could not run (%s)' % script)
        return None
    rc, out, err = r
    if rc not in (0, 1):
        warn('pending failed (exit %d)' % rc)
        return None
    try:
        data = json.loads(out)
        artifacts = [a for a in data.get('artifacts', []) if isinstance(a, dict)]
        queue = [e for e in data.get('queue', []) if isinstance(e, dict)]
        retired = [e for e in data.get('retired', []) if isinstance(e, dict) and e.get('url')]
    except (ValueError, AttributeError, TypeError):
        if rc == 0:
            return [], [], []
        warn('pending printed output that is not JSON (exit 1)')
        return None
    return artifacts, queue, retired


def only_full_progress(artifacts):
    """R8.11: Full Progress is the only artifact that is published; any other entry is ignored."""
    return [a for a in artifacts if a.get('kind') == 'full-progress' or a.get('key') == 'full-progress']


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
    sources = [os.path.join(worktree_dir(root), rel), 'origin',
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


def fingerprint(artifacts, queue, background=False, migration=False):
    """Stable hash of what is pending (keys and queued changes, not wording)."""
    parts = sorted([['artifact', str(a.get('key'))] for a in artifacts]
                   + [['event', str(e.get('id')), str(e.get('suggested_status'))] for e in queue]
                   + ([['background']] if background else [])
                   + ([['migration']] if migration else []))
    return hashlib.sha256(json.dumps(parts).encode('utf-8')).hexdigest()[:16]


def describe(artifacts, queue, background=False, migration=False):
    """One line per pending item, for the systemMessage."""
    lines = ['%s (%s)' % (a.get('title') or a.get('key'), a.get('file', '')) for a in artifacts]
    lines += ['%s -> %s' % (e.get('id'), e.get('suggested_status')) for e in queue]
    if background:
        lines.append(BACKGROUND_NOTE)
    if migration:
        lines.append(MIGRATION_NOTE)
    return '; '.join(lines)


def build_migration_reason(script, reasons):
    return ('The artifact record is in an older format (%s). Migrate it in this turn: run '
            'python "%s" render, then run pending --json.' % ('; '.join(reasons), script))


def retired_message(retired):
    return ('luismc-artifacts: old claude.ai pages of feature artifacts are still up (%s). They are deleted only '
            'with the owner\'s confirmation: ask the owner, delete each confirmed page with the Artifact tool '
            '(action: delete), then run mark-deleted.'
            % '; '.join('%s %s' % (e.get('key'), e.get('url')) for e in retired))


def tell_retired_once(root, sid, retired):
    """R8.13: the systemMessage listing retired pages, once per session and per list. '' when already told."""
    if not retired:
        return ''
    digest = hashlib.sha256(json.dumps(sorted(e['url'] for e in retired)).encode('utf-8')).hexdigest()[:16]
    path = os.path.join(root, STATE_NAME)
    state = read_state(path)
    entry = state.get('rule:' + sid) if isinstance(state.get('rule:' + sid), dict) else {}
    if entry.get('told') == digest:
        return ''
    entry['told'] = digest
    state.pop('rule:' + sid, None)
    state['rule:' + sid] = entry
    write_state(path, state)
    return retired_message(retired)


def build_reason(root, script, artifacts, queue):
    py = 'python "%s"' % script
    record = os.path.join(worktree_dir(root), 'docs', 'artifacts')
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
        # `path` is the publish copy (links to the feature files as file:/// URLs); the committed file is the fallback
        source = a.get('path') or os.path.join(record, str(a.get('file', '')))
        out.append('- Publish "%s" once, now, at the end of the turn (%s; %s): publish the file %s with the Artifact '
                   'tool, unedited (%s), then run: %s mark-published %s --url <the artifact URL>. Feature artifacts '
                   'are files in the repository and are never published.'
                   % (a.get('title') or key, a.get('file', ''), a.get('reason', 'pending'),
                      source, target, py, key))
    out.append('Then run %s pending --json to confirm nothing is left.' % py)
    return '\n'.join(out)


def build_background_reason(script):
    py = 'python "%s"' % script
    return ('Work was started in the background this turn but no task is Running. Record it with task-add '
            '(%s task-add --owner <key|project> --item ... --detail ... --expected ... --status Running) or '
            'set the task that covers it Running (%s set-task-status <ID> Running), then publish Full '
            'Progress if pending lists it. If the work is already finished, there is nothing to record: set its task '
            'Built only when it is finished, and release work still to come is its own task.' % (py, py))


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
    try:
        push_note = push_record(root, script)
    except Exception as exc:
        warn('record push skipped (%s: %s)' % (type(exc).__name__, exc))
        push_note = ''
    found = pending_items(root, script)
    # pending unreadable: fail open on artifacts, but the queue file is still a fact
    artifacts, queue, retired = found if found is not None else ([], [], [])
    try:
        reasons = migration_reasons_now(root, manifest)       # R8.14: read-only, the hook never migrates
    except Exception as exc:
        warn('migration check skipped (%s: %s)' % (type(exc).__name__, exc))
        reasons = []
    migration = bool(reasons)
    artifacts = only_full_progress(artifacts)
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
    try:
        told = tell_retired_once(root, sid, retired)      # R8.13: a message, never a block
    except Exception as exc:
        warn('retired pages not listed (%s: %s)' % (type(exc).__name__, exc))
        told = ''
    told = '\n'.join(part for part in (push_note, told) if part)
    if not artifacts and not queue and not background and not migration:
        state = read_state(state_path)
        if sid in state:
            del state[sid]
            write_state(state_path, state)
        if told:
            print(json.dumps({'systemMessage': told}))
        return 0
    state = read_state(state_path)
    digest = fingerprint(artifacts, queue, background, migration)
    blocks = entry.get('blocks', 0) if entry.get('last') == digest else 0
    if not isinstance(blocks, int):
        blocks = 0
    if blocks >= BLOCK_LIMIT:
        print(json.dumps({'systemMessage': '\n'.join(filter(None, [(
            'luismc-artifacts: letting the turn end after %d blocks with no change. Still unpublished, '
            'unapplied, unrecorded or unmigrated: %s. Run `pending` in the next session.'
            % (BLOCK_LIMIT, describe(artifacts, queue, background, migration))), told]))}))
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
    if migration:
        parts.insert(0, build_migration_reason(script, reasons))
    if background:
        parts.append(build_background_reason(script))
    out = {'decision': 'block', 'reason': '\n\n'.join(parts)}
    if told:
        out['systemMessage'] = told
    print(json.dumps(out))
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # fail open: a broken hook must not trap the session
        warn('end-of-turn hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
