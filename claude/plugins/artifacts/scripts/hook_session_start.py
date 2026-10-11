#!/usr/bin/env python3
"""Session-start hook (SessionStart).

ARTIFACTSPEC 1.2.0 section 8.3. Delivers the plugin's rule file as
`hookSpecificOutput.additionalContext` in any repository that has a record
manifest, every session, whether or not `gh` works (R8.9), followed by what the
session must do about the record: the old rule copy, a migration, old claude.ai
pages to delete (R8.13 to R8.15). Notes the delivery in the stop state so the
after-command hook does not repeat it (R8.12). Then catches up on
changes made outside a session: fetches the default branch, lists pull requests with `gh pr list`, and queues
`merged_status` for every task in Running, Waiting or To do whose branch `<ID>-*`
was merged, and `On hold` for one whose only pull requests were closed unmerged
(R8.5). When `gh` is missing or not signed in it queues nothing and prints one
systemMessage saying the catch-up was skipped (R8.6, fail open). It lists the
queued events in a systemMessage (R8.7). It only writes the queue (INV-4).

Seam for tests: CLAUDE_ARTIFACTS_GH overrides the gh executable (a .py path is
run with this interpreter).
Disable: CLAUDE_ARTIFACTS_HOOKS=off. Standard library only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hook_after_command import (RULE_HEADING, RULE_PATH, TASK_ID_RE, command_for, context_text,  # noqa: E402,F401
                                git, hook_root, hooks_off, load_manifest, mark_delivered,
                                merged_status_of, origin_record_file, parse_json, read_input,
                                rule_text, run, warn)

OPEN_STATUSES = ('Running', 'Waiting', 'To do')
GH_TIMEOUT = 30
FETCH_TIMEOUT = 25


def gh_command():
    return command_for(os.environ.get('CLAUDE_ARTIFACTS_GH') or 'gh')


def load_registry(root, branch):
    """The registry from origin/<branch> (the record's home), else the checkout."""
    text = origin_record_file(root, branch, 'registry.json')
    if text is None:
        path = os.path.join(root, 'docs', 'artifacts', 'registry.json')
        try:
            with open(path, encoding='utf-8') as f:
                text = f.read()
        except OSError:
            return None
    return parse_json(text, 'registry.json')


def list_pull_requests(root):
    """(prs, None) or (None, reason it was skipped)."""
    r = run(gh_command() + ['pr', 'list', '--state', 'all', '--json',
                            'headRefName,state,mergedAt', '--limit', '200'], root, GH_TIMEOUT)
    if r is None:
        return None, 'gh is not installed or did not answer'
    rc, out, _err = r
    if rc != 0:
        return None, 'gh is not signed in or failed (exit %d)' % rc
    try:
        prs = json.loads(out)
    except ValueError:
        return None, 'gh printed output that is not JSON'
    return [p for p in prs if isinstance(p, dict)] if isinstance(prs, list) else [], None


def outcomes_by_task(prs):
    """{task id: set of 'merged' | 'closed' | 'open'} over the pull requests' branches."""
    result = {}
    for pr in prs:
        m = TASK_ID_RE.match(str(pr.get('headRefName') or ''))
        if not m:
            continue
        state = str(pr.get('state') or '').upper()
        if state == 'MERGED' or pr.get('mergedAt'):
            kind = 'merged'
        elif state == 'CLOSED':
            kind = 'closed'
        else:
            kind = 'open'
        result.setdefault(m.group(1), set()).add(kind)
    return result


def rule_context(root, manifest):
    """The rule file's text, then what this session must do about the record, for additionalContext;
    '' when the plugin has no rule (R8.9, R8.12 to R8.15)."""
    return context_text(root, manifest)


def catch_up(root, manifest):
    """The pull request catch-up (R8.5 to R8.7); returns the systemMessage lines."""
    from artifact_queue import append_event, read_queue
    branch = manifest.get('default_branch') if isinstance(manifest.get('default_branch'), str) else 'main'
    merged_status = merged_status_of(manifest)
    messages = []

    f = git(root, 'fetch', 'origin', branch, timeout=FETCH_TIMEOUT)
    if f is None or f[0] != 0:
        warn('git fetch origin %s failed (exit %s)' % (branch, 'none' if f is None else f[0]))

    prs, skipped = list_pull_requests(root)
    if skipped:
        warn('gh pr list skipped: ' + skipped)
        messages.append('luismc-artifacts: the pull request catch-up was skipped (%s). '
                        'Statuses change only through commands this session runs.' % skipped)
    else:
        registry = load_registry(root, branch)
        tasks = registry.get('tasks') if isinstance(registry, dict) else None
        if not isinstance(tasks, list):
            warn('registry.json unreadable; catch-up skipped')
        else:
            outcomes = outcomes_by_task(prs)
            for task in tasks:
                if not isinstance(task, dict) or task.get('status') not in OPEN_STATUSES:
                    continue
                kinds = outcomes.get(task.get('id'), set())
                if 'merged' in kinds:
                    append_event(root, task['id'], merged_status, 'pull request merged')
                elif kinds == {'closed'}:
                    append_event(root, task['id'], 'On hold', 'pull request closed unmerged')

    events = read_queue(root)
    if events:
        listed = '; '.join('%s -> %s (%s)' % (e.get('id'), e.get('suggested_status'), e.get('event'))
                           for e in events)
        messages.append('luismc-artifacts: queued status changes waiting for this session: %s. '
                        'Apply or drop each before the turn ends.' % listed)
    return messages


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
    try:
        messages = catch_up(root, manifest)
    except Exception as exc:   # the rule below is still delivered
        warn('catch-up skipped (%s: %s)' % (type(exc).__name__, exc))
        messages = []
    out = {}
    if messages:
        out['systemMessage'] = '\n'.join(messages)
    try:
        context = rule_context(root, manifest)
    except Exception as exc:
        warn('rule not delivered (%s: %s)' % (type(exc).__name__, exc))
        context = ''
    if context:
        try:
            mark_delivered(root, str(data.get('session_id') or 'default'), rule_text())
        except Exception as exc:
            warn('delivery not recorded (%s: %s)' % (type(exc).__name__, exc))
        out['hookSpecificOutput'] = {'hookEventName': 'SessionStart', 'additionalContext': context}
    if out:
        print(json.dumps(out))
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # fail open
        warn('session-start hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
