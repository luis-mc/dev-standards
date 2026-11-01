#!/usr/bin/env python3
"""End-of-turn hook (Stop).

ARTIFACTSPEC 1.10.0 section 8.2. Lets the turn end only when the queue is empty and
`project_artifacts.py pending` lists nothing; otherwise blocks the stop with
{"decision": "block", "reason": ...} naming each item and the commands to run
(R8.3). It acts on Full Progress only, the one published artifact: a pending entry
for a feature artifact is ignored (R8.11). It also blocks when this session started background work (marked by
hook_after_command, R8.8) and the registry has no task in Running, Waiting or
Needs you (R8.10); once such a task exists the marker is cleared. After 3
consecutive blocks in one session with no change in what is pending it lets the
turn end and prints a systemMessage instead (R8.4), so a session that cannot
publish never loops. It never commits or pushes (AR50): it only reads the record (INV-4).

Per-session state: <repo>/.claude/artifacts-stop-state.json, shaped
{session_id: {"blocks": n, "last": <hash of what was pending>,
"background": {"started": <time>, ...}}}.

Seam for tests: CLAUDE_ARTIFACTS_SCRIPT overrides the path of project_artifacts.py.
Disable: CLAUDE_ARTIFACTS_HOOKS=off. Standard library only.
"""
import contextlib
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hook_after_command import (STATE_NAME, command_for, hook_root, hooks_off,  # noqa: E402
                                load_manifest, migration_reasons_now, origin_record_file,
                                parse_json, read_input, read_state, record_rel_of, run, script_path, warn,
                                worktree_dir, write_state)

BLOCK_LIMIT = 3          # R8.4; the ceiling in section 12 is 5, it may only be lowered
PENDING_TIMEOUT = 90
ACTIVE_STATUSES = ('Running', 'Waiting', 'Needs you')   # R8.10
try:
    import artifact_hourly as H
except ImportError:      # a broken install: the hourly and overdue checks are skipped
    H = None
BACKGROUND_NOTE = 'work started in the background with no Running task'
MIGRATION_NOTE = 'the artifact record needs migrating (run render)'


def run_pending_in_process(root):
    """(rc, stdout, stderr) of `project_artifacts.main(['pending', '--json'])` run in this process, from root, as the
    child would run it (same function, same working folder); None when it cannot be done, so the caller starts the
    child process instead. Used only for the plugin's own script, never for the test seam."""
    old_cwd = os.getcwd()
    try:
        import project_artifacts as PA
        out, err = io.StringIO(), io.StringIO()
        os.chdir(root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = PA.main(['pending', '--json'])
        finally:
            os.chdir(old_cwd)
        return (rc if isinstance(rc, int) else 0), out.getvalue(), err.getvalue()
    except (Exception, SystemExit):
        return None


def pending_items(root, script):
    """(artifacts, queue, retired, deferred) from `pending --json`; None when it cannot be read. Retired pages never
    change pending's exit code, so they are read from its output at exit 0 as well (R8.13)."""
    own = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'project_artifacts.py')
    r = None
    if os.path.abspath(script) == own:       # F4: one interpreter start less than a child process
        r = run_pending_in_process(root)
    if r is None:
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
        deferred = [e for e in data.get('deferred', []) if isinstance(e, dict)]
    except (ValueError, AttributeError, TypeError):
        if rc == 0:
            return [], [], [], []
        warn('pending printed output that is not JSON (exit 1)')
        return None
    return artifacts, queue, retired, deferred


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
    """The task list from the freshest registry: the working tree, else origin/<branch>. None when none can be read."""
    branch = manifest.get('default_branch') if isinstance(manifest.get('default_branch'), str) else 'main'
    rel = os.path.join(*record_rel_of(root).split('/'), 'registry.json')
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


def freshness(root, manifest, artifacts):
    """R8.18, R8.19, R9.8 to R9.10, R6.14: (stale, overdue). `stale` is a list of reasons to publish Full Progress although
    pending does not list it (published over 60 minutes ago, or a release task changed since); `overdue` is
    [(task, expected)] for open rows whose Expected time has passed. Both [] when Full Progress was never
    published or the registry cannot be read (fail open)."""
    if H is None:
        return [], []
    tasks = registry_tasks(root, manifest) or []
    stale = []
    if not artifacts:       # pending already lists it: the publish below covers these too
        mins = H.hourly_due(manifest)
        if mins is not None:
            stale.append('Full Progress was last published %d minutes ago (hourly fail-safe, limit %d)'
                         % (mins, H.STALE_MINUTES))
        for t in H.release_changes(tasks, manifest):
            stale.append('release task %s changed to %s after the last publish' % (t.get('id'), t.get('status')))
    return stale, H.overdue_tasks(tasks, manifest)


def fingerprint(artifacts, queue, background=False, migration=False, stale=(), overdue=()):
    """Stable hash of what is pending (keys and queued changes, not wording)."""
    parts = sorted([['artifact', str(a.get('key'))] for a in artifacts]
                   + [['event', str(e.get('id')), str(e.get('suggested_status'))] for e in queue]
                   + ([['background']] if background else [])
                   + ([['migration']] if migration else [])
                   + [['stale', 'hourly' if r.startswith('Full Progress') else r.split()[2]] for r in stale]
                   + [['overdue', str(t.get('id')), str(t.get('expected'))] for t, _w in overdue])
    return hashlib.sha256(json.dumps(parts).encode('utf-8')).hexdigest()[:16]


def describe(artifacts, queue, background=False, migration=False, stale=(), overdue=()):
    """One line per pending item, for the systemMessage."""
    lines = ['%s (%s)' % (a.get('title') or a.get('key'), a.get('file', '')) for a in artifacts]
    lines += ['%s -> %s' % (e.get('id'), e.get('suggested_status')) for e in queue]
    if background:
        lines.append(BACKGROUND_NOTE)
    if migration:
        lines.append(MIGRATION_NOTE)
    lines += list(stale)
    lines += [H.overdue_text(t) for t, _w in overdue]
    return '; '.join(lines)


def build_migration_reason(script, reasons):
    return ('The artifact record is in an older format (%s). Migrate it in this turn: run '
            'python "%s" render, then run pending --json.' % ('; '.join(reasons), script))


def retired_message(retired):
    return ('luismc-artifacts: old claude.ai pages of feature artifacts are still up (%s). They are deleted only '
            'with the owner\'s confirmation: ask the owner, delete each confirmed page with the Artifact tool '
            '(action: delete), then run mark-deleted.'
            % '; '.join('%s %s' % (e.get('key'), e.get('url')) for e in retired))


def tell_once(root, sid, field, digest, message):
    """A systemMessage told once per session and per `digest` (kept in the stop state). '' when already told."""
    path = os.path.join(root, STATE_NAME)
    state = read_state(path)
    entry = state.get('rule:' + sid) if isinstance(state.get('rule:' + sid), dict) else {}
    if entry.get(field) == digest:
        return ''
    entry[field] = digest
    state.pop('rule:' + sid, None)
    state['rule:' + sid] = entry
    write_state(path, state)
    return message


def tell_retired_once(root, sid, retired):
    """R8.13: the systemMessage listing retired pages, once per session and per list. '' when already told."""
    if not retired:
        return ''
    digest = hashlib.sha256(json.dumps(sorted(e['url'] for e in retired)).encode('utf-8')).hexdigest()[:16]
    return tell_once(root, sid, 'told', digest, retired_message(retired))


def deferred_message(deferred):
    return ("luismc-artifacts: the Full Progress publish is deferred (claude.ai's daily limit): %s. Not asking for it "
            "before then; the end of the turn does not block on it."
            % '; '.join(str(e.get('reason') or 'deferred') for e in deferred))


def tell_deferred_once(root, sid, deferred):
    """R9.7: one line saying the publish is deferred and until when, once per session and per deferral."""
    if not deferred:
        return ''
    digest = hashlib.sha256(json.dumps(sorted(str(e.get('until')) for e in deferred)).encode('utf-8')).hexdigest()[:16]
    return tell_once(root, sid, 'deferred', digest, deferred_message(deferred))


def build_reason(root, script, artifacts, queue):
    py = 'python "%s"' % script
    record = os.path.join(worktree_dir(root), *record_rel_of(root).split('/'))
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


def build_stale_reason(script, stale):
    py = 'python "%s"' % script
    return ('Full Progress must be published again: %s. Finish this in the same turn: run %s pending --json --refresh, '
            'publish the file it names with the Artifact tool, unedited, then run %s mark-published full-progress '
            '--url <the artifact URL>.' % ('; '.join(stale), py, py))


def build_overdue_reason(script, overdue):
    py = 'python "%s"' % script
    rows = '; '.join(H.overdue_text(t) for t, _w in overdue)
    return ('Open rows are past their Expected time: %s. Set the real status or a new Expected for each (%s '
            'set-task-status <ID> <status> --expected "DD Mon ~HH:MM"), then publish Full Progress if pending lists it.'
            % (rows, py))


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
    found = pending_items(root, script)
    # pending unreadable: fail open on artifacts, but the queue file is still a fact
    artifacts, queue, retired, deferred = found if found is not None else ([], [], [], [])
    try:
        reasons = migration_reasons_now(root, manifest)       # R8.14: read-only, the hook never migrates
    except Exception as exc:
        warn('migration check skipped (%s: %s)' % (type(exc).__name__, exc))
        reasons = []
    migration = bool(reasons)
    artifacts = only_full_progress(artifacts)
    queue = merge_queue(root, queue)
    try:
        stale, overdue = freshness(root, manifest, artifacts)
    except Exception as exc:
        warn('hourly and overdue checks skipped (%s: %s)' % (type(exc).__name__, exc))
        stale, overdue = [], []
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
    try:
        told_deferred = tell_deferred_once(root, sid, only_full_progress(deferred))      # R9.7: a message, never a block
    except Exception as exc:
        warn('deferred publish not listed (%s: %s)' % (type(exc).__name__, exc))
        told_deferred = ''
    told = '\n'.join(part for part in (told, told_deferred) if part)
    if not artifacts and not queue and not background and not migration and not stale and not overdue:
        state = read_state(state_path)
        if sid in state:
            del state[sid]
            write_state(state_path, state)
        if told:
            print(json.dumps({'systemMessage': told}))
        return 0
    state = read_state(state_path)
    digest = fingerprint(artifacts, queue, background, migration, stale, overdue)
    blocks = entry.get('blocks', 0) if entry.get('last') == digest else 0
    if not isinstance(blocks, int):
        blocks = 0
    if blocks >= BLOCK_LIMIT:
        print(json.dumps({'systemMessage': '\n'.join(filter(None, [(
            'luismc-artifacts: letting the turn end after %d blocks with no change. Still unpublished, '
            'unapplied, unrecorded or unmigrated: %s. Run `pending` in the next session.'
            % (BLOCK_LIMIT, describe(artifacts, queue, background, migration, stale, overdue))), told]))}))
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
    if stale:
        parts.append(build_stale_reason(script, stale))
    if overdue:
        parts.append(build_overdue_reason(script, overdue))
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
