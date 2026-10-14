#!/usr/bin/env python3
"""PreToolUse hook (DELIVERYSPEC section 5: D4, D8 Q-3 and Q-4; section 1 ids).

Denies a Bash, Agent, RemoteTrigger, AskUserQuestion or Write call that breaks a delivery
rule, with a one-line reason that names the DL id and the fix, as
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}.
Reads the ledger and .delivery/config.json read-only. A project without .delivery/ is
untouched; an error in the hook allows the call (fail open).

Checks: DL-05 06 07 20 23 36 37 38 41 42 53 55 73 74 75, D4 (PC-bound), Q-3, Q-4.
"""
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooklib as H  # noqa: E402

ATTRIBUTION_RE = re.compile(r'co-authored-by|generated with \[?claude|claude code|noreply@anthropic\.com|'
                            r'\U0001F916 generated|written by claude|\bclaude-session\b', re.I)
LOCKFILE_OK = ('--frozen-lockfile', '--immutable', 'ci')
PC_BOUND_RE = re.compile(r'^\s*PC-bound:\s*\S', re.M | re.I)


class Deny(Exception):
    pass


def deny(reason):
    raise Deny(reason)


def flag(tokens, *names):
    return any(t in names or any(t.startswith(n + '=') for n in names if n.startswith('--')) for t in tokens)


# --- Bash --------------------------------------------------------------------------------

def pr_arg(tokens):
    """The PR selector after `gh pr merge` (number, url or branch); None when absent."""
    rest = H.strip_prefix(tokens)[3:]
    skip = False
    for t in rest:
        if skip:
            skip = False
            continue
        if t in ('--body', '-b', '--subject', '-t', '--match-head-commit', '--body-file', '-F', '--repo', '-R'):
            skip = True
            continue
        if not t.startswith('-'):
            return t
    return None


def check_merge(root, seg, ledger):
    if flag(seg, '--auto'):
        deny('DL-05 gh pr merge --auto is never used. Wait for ci_watch.py to pass for the current head, then run '
             'gh pr merge without --auto.')
    arg = pr_arg(seg)
    ref = [arg] if arg else []
    r = H.gh(root, ['pr', 'view'] + ref + ['--json', 'number,headRefOid'])
    number, head = None, None
    if r and r[0] == 0:
        try:
            j = json.loads(r[1])
            number, head = j.get('number'), j.get('headRefOid')
        except ValueError:
            pass
    if number is None and arg and arg.isdigit():
        number = int(arg)
    trains = [t for t in ledger['trains'] if number is not None and t.get('pr') == number]
    ok = [t for t in trains if (t.get('ci') or {}).get('state') == 'success'
          and (head is None or (t.get('ci') or {}).get('head_sha') == head)]
    if not ok:
        deny('DL-06 no ledger CI success for the current head of PR %s. Run ci_watch.py for the head commit '
             '(delivery_ledger records it), then merge.' % (number if number is not None else arg or 'N'))


def check_unfrozen(seg, command, cfg):
    t = [x.lower() for x in H.strip_prefix(seg)]
    if '--no-frozen-lockfile' in t:
        deny('DL-23 never install without a frozen lockfile. If the gate failed at setup the lockfile is stale: '
             'regenerate it and commit, then re-run the gate.')
    if not t or t[0] not in ('npm', 'pnpm', 'yarn', 'bun'):
        return
    sub = t[1] if len(t) > 1 else ''
    installing = sub in ('install', 'i', 'add') or (t[0] == 'yarn' and len(t) == 1)
    if installing and not any(f in t for f in ('--frozen-lockfile', '--immutable', '--ci')):
        if any(m.lower() in command.lower() for m in cfg['gate_markers']):
            deny('DL-23 no unfrozen install in a gate context. Use npm ci / pnpm install --frozen-lockfile; a stale '
                 'lockfile is regenerated and committed, never installed around.')


def check_kill(seg, command):
    t = [x.lower() for x in H.strip_prefix(seg)]
    prog = t[0] if t else ''
    msg = ('DL-42 stop only processes and containers you started: kill by the pid or container id you recorded in '
           'the ledger, never by name or all at once.')
    if prog in ('pkill', 'killall'):
        deny(msg)
    if prog == 'taskkill' and any(x in ('/im', '-im') for x in t):
        deny(msg)
    if prog == 'docker' and any(x in ('stop', 'kill', 'rm') for x in t) and any('$(' in x or '`' in x for x in t):
        deny(msg)
    if re.search(r'docker\s+(?:container\s+)?ls?\b[^|;&]*\|\s*xargs\s+docker|docker\s+ps[^|;&]*\|\s*xargs\s+docker|'
                 r'\$\(\s*docker\s+(?:ps|container\s+ls)', command):
        deny(msg)
    if prog == 'kill' and any('$(pgrep' in x or '`pgrep' in x for x in t):
        deny(msg)


def norm_path(p):
    return os.path.normpath(p.replace('\\', '/')).replace('\\', '/').rstrip('/').lower()


def check_worktree(seg, cfg, cwd):
    t = H.strip_prefix(seg)
    if len(t) < 3 or t[0].lower() != 'git' or 'worktree' not in t or 'add' not in t[t.index('worktree'):]:
        return
    root = cfg.get('work_root')
    if not root:
        return
    args = t[t.index('add') + 1:]
    path, skip = None, False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ('-b', '-B', '--reason'):
            skip = True
            continue
        if not a.startswith('-'):
            path = a
            break
    if not path:
        return
    full = path if re.match(r'^([A-Za-z]:)?[\\/]', path) else os.path.join(cwd, path)
    base = norm_path(root)
    p = norm_path(full)
    if p != base and not p.startswith(base + '/'):
        deny('DL-53 worktrees live under the work root %s, not %s. Re-run git worktree add with a path under it '
             'and remove it when done.' % (root, path))


def check_install(seg, command, ledger, cfg, at):
    t = [x.lower() for x in H.strip_prefix(seg)]
    is_install = bool(t) and (t[0] == 'msiexec' or (t[0] == 'schtasks' and '/run' in t and 'updatenow' in command.lower()))
    if not is_install:
        return
    for i in ledger['installs']:
        age = H.minutes_since(i.get('started'), at)
        if i.get('state') == 'installing' and (age is None or age < cfg['install_stale_min']):
            deny('DL-55 an install of %s is already running (started %s). Wait for it to finish (installs[] state '
                 'done/failed), then start this one.' % (i.get('product'), i.get('started')))


def check_send(seg, cfg):
    t = H.strip_prefix(seg)
    for pat in cfg['send_deny']:
        words = pat.split()
        if words and H.starts_with(t, words):
            deny('DL-73 never send in the owner\'s name (%s). Write the text to a draft file under docs/ and tell '
                 'the owner.' % pat)


def check_attribution(seg, command, cfg):
    if not cfg.get('no_attribution'):
        return
    if (H.starts_with(seg, ['git', 'commit']) or H.starts_with(seg, ['gh', 'pr', 'create'])
            or H.starts_with(seg, ['gh', 'pr', 'edit'])) and ATTRIBUTION_RE.search(command):
        deny('DL-74 no Co-Authored-By or AI attribution in commits or PR bodies (config no_attribution). '
             'Remove those lines from the message or body.')


def check_bash(root, cfg, ledger, data, at):
    command = (data.get('tool_input') or {}).get('command') or ''
    cwd = data.get('cwd') if isinstance(data.get('cwd'), str) else root
    for seg in H.segments(command):
        if H.starts_with(seg, ['gh', 'pr', 'merge']) and H.check_on(cfg, 'DL-05'):
            check_merge(root, seg, ledger)
        if H.starts_with(seg, ['gh', 'pr', 'checks']) and flag(seg, '--watch') and H.check_on(cfg, 'DL-07'):
            deny('DL-07 do not watch the PR check list. Watch the workflow runs of the head commit: ci_watch.py <sha>.')
        if H.starts_with(seg, ['vercel', 'env', 'rm']) and H.check_on(cfg, 'DL-20'):
            deny('DL-20 never vercel env rm to narrow targets (it deletes every target). Use vercel env update or '
                 'rm and re-add with all needed targets, then re-list Production.')
        if H.check_on(cfg, 'DL-23'):
            check_unfrozen(seg, command, cfg)
        if H.check_on(cfg, 'DL-42'):
            check_kill(seg, command)
        if H.check_on(cfg, 'DL-53'):
            check_worktree(seg, cfg, cwd)
        if H.check_on(cfg, 'DL-55'):
            check_install(seg, command, ledger, cfg, at)
        if H.check_on(cfg, 'DL-73'):
            check_send(seg, cfg)
        if H.check_on(cfg, 'DL-74'):
            check_attribution(seg, command, cfg)


# --- Write ---------------------------------------------------------------------------------

def check_write(root, cfg, data):
    path = (data.get('tool_input') or {}).get('file_path') or ''
    if not path.lower().endswith('.md') or not H.check_on(cfg, 'DL-75'):
        return
    full = os.path.abspath(path if os.path.isabs(path) else os.path.join(root, path))
    rel = os.path.relpath(full, root).replace('\\', '/')
    if rel.startswith('../') or rel == '..':
        return                                   # outside the project: not ours
    base = os.path.basename(rel).lower()
    if rel.startswith('docs/') or rel.startswith('.claude/') or base.startswith(('readme', 'claude')):
        return
    if any(fnmatch.fnmatch(rel, g) for g in cfg['md_allow']):
        return
    deny('DL-75 create every doc under docs/ (README, CLAUDE.md and .claude/ excepted). Write it to docs/%s.' % base)


# --- Agent and RemoteTrigger ---------------------------------------------------------------

def walk(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k, v
            for kv in walk(v):
                yield kv
    elif isinstance(value, list):
        for v in value:
            for kv in walk(v):
                yield kv


def find_key(value, *names):
    for k, v in walk(value):
        if k in names and isinstance(v, (str, int, float)) and str(v).strip():
            return v
    return None


def brief_text(tool_input):
    return '\n'.join(v for k, v in walk(tool_input) if isinstance(v, str))


def delivery_block(text):
    """Key/value pairs from the fenced ```delivery block of a brief; owns as a list."""
    m = re.search(r'```delivery\s*\n(.*?)```', text, re.S)
    out = {'owns': []}
    if not m:
        return out
    key = None
    for line in m.group(1).splitlines():
        item = re.match(r'^\s*-\s+(.+?)\s*$', line)
        kv = re.match(r'^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$', line)
        if item and key == 'owns':
            out['owns'].append(item.group(1).strip('\'"'))
        elif kv:
            key = kv.group(1).lower()
            if key == 'owns':
                out['owns'] += [x.strip().strip('\'"') for x in kv.group(2).strip('[]').split(',') if x.strip()]
            else:
                out[key] = kv.group(2)
    return out


def prefix(glob):
    g = glob.replace('\\', '/').lstrip('./')
    m = re.search(r'[*?\[]', g)
    return (g[:m.start()] if m else g).rstrip('/')


def overlaps(a, b):
    pa, pb = prefix(a), prefix(b)
    if not pa or not pb:
        return True
    sa, sb = pa + '/', pb + '/'
    return pa == pb or sa.startswith(sb) or sb.startswith(sa) or fnmatch.fnmatch(pa, b) or fnmatch.fnmatch(pb, a)


def free_gb():
    v = os.environ.get('DELIVERY_FREE_GB')
    if v:
        try:
            return float(v)
        except ValueError:
            return None
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / 1048576.0
    except (OSError, ValueError):
        pass
    return None


def check_launch(cfg, ledger, data, where):
    ti = data.get('tool_input') or {}
    if where == 'cloud':
        action = str(ti.get('action') or '').lower()
        if action not in ('create', 'run', 'update') or not isinstance(ti.get('body') or ti.get('prompt'), (dict, str)):
            return
    text = brief_text(ti)
    block = delivery_block(text)
    cloud_running = len(H.running_agents(ledger, 'cloud'))
    local_running = len(H.running_agents(ledger, 'local'))
    cap_cloud, cap_local = int(cfg['caps'].get('cloud', 8)), int(cfg['caps'].get('local', 3))
    if where == 'local' and H.check_on(cfg, 'D4') and cloud_running < cap_cloud and not PC_BOUND_RE.search(text):
        deny('D4 run non-PC-bound work in the cloud (cloud running %d of %d). Launch it with RemoteTrigger, or add a '
             '"PC-bound: <reason>" line to this brief.' % (cloud_running, cap_cloud))
    model = find_key(ti, 'model')
    effort = find_key(ti, 'effort_level') if where == 'cloud' else (find_key(ti, 'effort') or block.get('effort'))
    if not model and H.check_on(cfg, 'DL-37'):
        deny('DL-37 set the model (Sonnet at medium for code agents; Opus at medium) on this %s launch.'
             % ('RemoteTrigger session_context' if where == 'cloud' else 'Agent call'))
    if not effort and H.check_on(cfg, 'DL-37'):
        deny('DL-37 set %s on this launch (medium for code agents).'
             % ('session_context.effort_level' if where == 'cloud'
                else 'effort: an "effort: medium" line in the delivery block of the brief'))
    missing = [m for m in cfg['brief_markers'] if m.lower() not in text.lower()]
    if missing and H.check_on(cfg, 'DL-36'):
        deny('DL-36 the brief lacks required markers: %s. Add them (config brief_markers), then launch.'
             % '; '.join(missing))
    if H.check_on(cfg, 'DL-38'):
        if where == 'cloud' and cloud_running >= cap_cloud:
            deny('DL-38 cloud cap reached (%d running of %d). Wait for one to finish or ask the owner to raise the cap '
                 'in .delivery/config.json.' % (cloud_running, cap_cloud))
        if where == 'local':
            if local_running >= cap_local:
                deny('DL-38 local cap reached (%d running of %d). Wait for one to finish.' % (local_running, cap_local))
            free = free_gb()
            if free is not None and free <= float(cfg['min_free_gb']):
                deny('DL-38 local agents need more than %s GB free memory (%.1f GB free). Use a cloud run or wait.'
                     % (cfg['min_free_gb'], free))
    if H.check_on(cfg, 'DL-41') and block['owns']:
        for a in H.running_agents(ledger):
            for mine in block['owns']:
                for theirs in a.get('owns') or []:
                    if isinstance(theirs, str) and overlaps(mine, theirs):
                        deny('DL-41 files "%s" overlap "%s" owned by running agent %s. Split by file ownership or wait '
                             'for that agent to finish.' % (mine, theirs, a.get('task') or a.get('id')))


# --- AskUserQuestion -------------------------------------------------------------------------

def check_question(cfg, ledger, data, at):
    qs = (data.get('tool_input') or {}).get('questions')
    minc = int(cfg['min_question_chars'])
    if H.check_on(cfg, 'Q-3') and isinstance(qs, list):
        for q in qs:
            text = q.get('question') if isinstance(q, dict) else None
            if not isinstance(text, str) or len(text.strip()) < minc:
                deny('Q-3 a question text is shorter than %d characters. Put the context inside each question text '
                     '(text before the dialog is not seen) so it stands alone.' % minc)
    if H.check_on(cfg, 'Q-4'):
        todo = ['%s is green and unmerged' % H.release_name(t) for t in H.trains_green_unmerged(ledger, at)]
        todo += ['%s is joined and not pushed' % H.release_name(t) for t in H.trains_joined_unpushed(ledger, at, 0)]
        todo += ['agent %s is queued to launch' % (a.get('task') or a.get('id')) for a in ledger['agents']
                 if a.get('state') == 'queued']
        if todo:
            deny('Q-4 do the actions that do not need the answer first (%s): merge, push or launch, then ask.'
                 % '; '.join(todo[:3]))


def main():
    if H.hooks_off():
        return 0
    data = H.read_input()
    root = H.find_root(data)
    if not root:
        return 0
    cfg = H.load_config(root)
    ledger = H.load_ledger(root)
    at = H.now()
    tool = data.get('tool_name')
    try:
        if tool == 'Bash':
            check_bash(root, cfg, ledger, data, at)
        elif tool == 'Write':
            check_write(root, cfg, data)
        elif tool == 'Agent':
            check_launch(cfg, ledger, data, 'local')
        elif tool == 'RemoteTrigger':
            check_launch(cfg, ledger, data, 'cloud')
        elif tool == 'AskUserQuestion':
            check_question(cfg, ledger, data, at)
    except Deny as d:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                 'permissionDecisionReason': str(d)}}))
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # fail open
        H.warn('pre-tool hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
