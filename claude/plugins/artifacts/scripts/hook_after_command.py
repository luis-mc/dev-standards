#!/usr/bin/env python3
"""After-command hook (PostToolUse and PostToolUseFailure for Bash; PostToolUse for Agent and Task).

ARTIFACTSPEC 1.1.0 section 8.1. Takes the task ID from the current branch name,
and when the command that just ran is one of the table rows, appends a status
event to the queue <repo>/.claude/artifacts-queue.json. It only queues: it never
writes the record (INV-4, R8.1), finishes fast and never fails the tool call
(R8.2): every error is one line on stderr and exit 0.

It also notes background work (R8.8): an `Agent` or `Task` call, or a `Bash` call
with `run_in_background` true, stamps the session's entry in
<repo>/.claude/artifacts-stop-state.json so the end-of-turn hook can ask for a
Running task. That file is session state, not the record.

Claude Code sends a successful Bash call as PostToolUse and a failed one (exit
code not 0) as PostToolUseFailure, whose `error` field starts with
`Exit code N`. The plugin's hooks.json registers this script for both events.

This file also holds the helpers the other two hooks import (switch, input,
manifest lookup, subprocess seams). Standard library only.

Disable: CLAUDE_ARTIFACTS_HOOKS=off.
"""
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DISABLE_VALUES = {'off', '0', 'false', 'no'}
TASK_ID_RE = re.compile(r'^([A-Z]{2,5}[0-9]+)-')
MANIFEST_REL = 'manifest.json'
STATE_NAME = os.path.join('.claude', 'artifacts-stop-state.json')
MAX_SESSIONS = 20
BACKGROUND_TOOLS = ('Agent', 'Task')


# --- shared helpers (also imported by hook_end_of_turn and hook_session_start) --------

def hooks_off():
    return os.environ.get('CLAUDE_ARTIFACTS_HOOKS', 'on').strip().lower() in DISABLE_VALUES


def warn(message):
    """One line on stderr naming the dependency and the exit code (R8.2, R11.1)."""
    try:
        print('luismc-artifacts: ' + message.replace('\n', ' '), file=sys.stderr)
    except Exception:
        pass


def read_input():
    """The hook's JSON from stdin; {} when empty or not a JSON object."""
    try:
        text = sys.stdin.buffer.read().decode('utf-8', 'replace')
        data = json.loads(text) if text.strip() else {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def command_for(path):
    """Argv prefix for a seam path: a .py file is run with this interpreter."""
    if path.lower().endswith('.py'):
        return [sys.executable, path]
    return [path]


def run(argv, cwd, timeout):
    """(returncode, stdout, stderr), or None when it cannot start or times out."""
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return (p.returncode, p.stdout.decode('utf-8', 'replace'),
            p.stderr.decode('utf-8', 'replace'))


def git(root, *args, timeout=10):
    return run(['git'] + list(args), root, timeout)


def candidate_branches(root):
    """Possible default branch names, most likely first."""
    names = []
    r = git(root, 'symbolic-ref', '--short', '-q', 'refs/remotes/origin/HEAD')
    if r and r[0] == 0 and r[1].strip().startswith('origin/'):
        names.append(r[1].strip()[len('origin/'):])
    for n in ('main', 'master'):
        if n not in names:
            names.append(n)
    return names


def origin_record_file(root, branch, rel):
    r = git(root, 'show', 'origin/%s:docs/artifacts/%s' % (branch, rel))
    return r[1] if r and r[0] == 0 else None


def parse_json(text, what):
    try:
        data = json.loads(text)
    except ValueError:
        warn('%s is not valid JSON' % what)
        return None
    return data if isinstance(data, dict) else None


def load_manifest(root):
    """The manifest in the current checkout, else on origin/<default branch>; None if neither."""
    path = os.path.join(root, 'docs', 'artifacts', MANIFEST_REL)
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                return parse_json(f.read(), path)
        except OSError:
            warn('cannot read %s' % path)
            return None
    for branch in candidate_branches(root):
        text = origin_record_file(root, branch, MANIFEST_REL)
        if text is not None:
            return parse_json(text, 'origin/%s:docs/artifacts/manifest.json' % branch)
    return None


def merged_status_of(manifest):
    """The status a merge suggests: `Live` (default) or `Built`; the old `Done` reads as `Built`."""
    value = manifest.get('merged_status')
    return 'Built' if value in ('Built', 'Done') else 'Live'


def read_state(path):
    """The per-session stop state (see hook_end_of_turn); {} when missing or unreadable."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(path, state):
    if len(state) > MAX_SESSIONS:
        for k in list(state)[:len(state) - MAX_SESSIONS]:
            del state[k]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = '%s.%d.tmp' % (path, os.getpid())
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(state, f, indent=1)
        f.write('\n')
    os.replace(tmp, path)


def hook_root(data):
    """Repository root for the hook: the input's cwd when it is a directory, else our cwd."""
    from artifact_queue import repo_root
    cwd = data.get('cwd')
    start = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else None
    return repo_root(start)


# --- after-command hook ----------------------------------------------------------------

MERGED = object()   # sentinel: the manifest's merged_status
SEPARATORS = re.compile(r'&&|\|\||[;|&\n]')
WRAPPERS = {'rtk', 'proxy', 'env', 'time', 'command', 'exec', 'nohup', 'npx', 'bunx', 'sudo'}
PYTHONS = {'python', 'python3', 'py', 'python.exe', 'python3.exe', 'py.exe'}
EXIT_RE = re.compile(r'(?m)^\s*Exit code (-?\d+)')


def exit_code(data):
    """Exit code of the Bash call, or None when unknown or interrupted (queue nothing).

    PostToolUse means the call succeeded (0). PostToolUseFailure carries
    `Exit code N` as the first line of `error`. As a fallback for other shapes a
    numeric exit field of tool_response, or a string tool_response with an
    `Exit code N` line, is honoured.
    """
    if data.get('is_interrupt') is True:
        return None
    resp = data.get('tool_response')
    if isinstance(resp, dict):
        if resp.get('interrupted'):
            return None
        for key in ('exit_code', 'exitCode', 'returncode', 'code'):
            if isinstance(resp.get(key), int) and not isinstance(resp.get(key), bool):
                return resp[key]
    text = data.get('error') if isinstance(data.get('error'), str) else (
        resp if isinstance(resp, str) else '')
    m = EXIT_RE.match(text) if data.get('error') else EXIT_RE.search(text)
    if m:
        return int(m.group(1))
    if data.get('hook_event_name') == 'PostToolUseFailure' or data.get('error'):
        return None   # failed, but no exit code to read
    return 0


def segment_tokens(segment):
    seg = segment.replace('\\', '/').strip().lstrip('({ ')
    try:
        tokens = shlex.split(seg)
    except ValueError:
        tokens = seg.split()
    while tokens:
        t = tokens[0]
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', t) or t in WRAPPERS:
            tokens.pop(0)
        elif t.lower() in PYTHONS:
            tokens.pop(0)
            while tokens and tokens[0].startswith('-'):
                tokens.pop(0)
        else:
            break
    return tokens


def classify_segment(tokens, code):
    """List of (suggested status or MERGED, event) for one command segment."""
    if not tokens:
        return []
    head = posixpath.basename(tokens[0]).lower()
    if head == 'gh' and len(tokens) >= 3:
        sub = tuple(tokens[1:3])
        if code == 0 and sub == ('pr', 'create'):
            return [('Running', 'gh pr create')]
        if code == 0 and sub == ('pr', 'ready'):
            return [('Waiting', 'gh pr ready')]
        if code == 0 and sub == ('pr', 'merge'):
            if '--auto' in tokens or '--disable-auto' in tokens:
                return []   # merge is only scheduled, not done
            return [(MERGED, 'gh pr merge')]
        if sub == ('run', 'watch'):
            return [('Failed', 'gh run watch failed')] if code else [('Waiting', 'gh run watch passed')]
    if head == 'ci_watch.py':
        return [('Failed', 'ci_watch failed')] if code else [('Waiting', 'ci_watch passed')]
    if code == 0:
        if head == 'vercel' and ('--prod' in tokens or '--production' in tokens):
            return [('Live', 'vercel deploy --prod')]
        if head in ('fly', 'flyctl') and len(tokens) > 1 and tokens[1] == 'deploy':
            return [('Live', 'fly deploy')]
        if head == 'wrangler' and len(tokens) > 1 and tokens[1] == 'deploy':
            return [('Live', 'wrangler deploy')]
        if head == 'firebase' and len(tokens) > 1 and tokens[1] == 'deploy':
            return [('Live', 'firebase deploy')]
    return []


def classify(command, code):
    found = []
    for seg in SEPARATORS.split(command):
        for item in classify_segment(segment_tokens(seg), code):
            if item not in found:
                found.append(item)
    return found


def current_task_id(root):
    r = git(root, 'symbolic-ref', '--short', '-q', 'HEAD')
    if not r or r[0] != 0:
        return None
    m = TASK_ID_RE.match(r[1].strip())
    return m.group(1) if m else None


def starts_background_work(data):
    """True for a successful Agent or Task call, or a Bash call run in the background (R8.8)."""
    if data.get('hook_event_name') == 'PostToolUseFailure' or data.get('error'):
        return False   # nothing was started
    tool = data.get('tool_name', 'Bash')
    if tool in BACKGROUND_TOOLS:
        return True
    tool_input = data.get('tool_input')
    return tool == 'Bash' and isinstance(tool_input, dict) and tool_input.get('run_in_background') is True


def note_background_work(data):
    """Stamp the session's entry in the stop state; the record is not touched (INV-4)."""
    root = hook_root(data)
    if not root or load_manifest(root) is None:
        return
    path = os.path.join(root, STATE_NAME)
    sid = str(data.get('session_id') or 'default')
    state = read_state(path)
    entry = state.get(sid) if isinstance(state.get(sid), dict) else {}
    entry['background'] = {'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'session_id': sid,
                           'tool': str(data.get('tool_name', 'Bash'))}
    state.pop(sid, None)   # keeps the most recently used session last
    state[sid] = entry
    write_state(path, state)


def main():
    if hooks_off():
        return 0
    data = read_input()
    if starts_background_work(data):
        try:
            note_background_work(data)
        except Exception as exc:   # a marker that cannot be written must not stop the queueing below
            warn('background marker skipped (%s: %s)' % (type(exc).__name__, exc))
    if data.get('tool_name', 'Bash') != 'Bash':
        return 0
    tool_input = data.get('tool_input')
    command = tool_input.get('command') if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0
    code = exit_code(data)
    if code is None:
        return 0
    events = classify(command, code)
    if not events:
        return 0
    root = hook_root(data)
    if not root:
        return 0
    task_id = current_task_id(root)
    if not task_id:
        return 0
    manifest = load_manifest(root)
    if manifest is None:
        return 0
    from artifact_queue import append_event
    merged_status = merged_status_of(manifest)
    for status, event in events:
        append_event(root, task_id, merged_status if status is MERGED else status, event, command)
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # R8.2: never fail the tool call
        warn('after-command hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
