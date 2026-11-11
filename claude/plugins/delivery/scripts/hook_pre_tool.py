#!/usr/bin/env python3
"""PreToolUse hook (DELIVERYSPEC section 5: D4, D8 Q-3 and Q-4; section 1 ids).

Denies a Bash, Agent, RemoteTrigger, AskUserQuestion or Write call that breaks a delivery
rule, with a one-line reason that names the DL id and the fix, as
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}.
Reads the ledger and .delivery/config.json read-only. A project without .delivery/ is
untouched; an error in the hook allows the call (fail open).

Checks: DL-77 (load guard, exit 2), DL-94 (workflow tool downloads), DL-11 (no branch gate on a join), DL-05 06 07 20 23 36 37 38 41 42 53 55 73 74 75, D4 (PC-bound), Q-3, Q-4.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooklib as H  # noqa: E402
import load_guard as G  # noqa: E402

ATTRIBUTION_RE = re.compile(r'co-authored-by|generated with \[?claude|claude code|noreply@anthropic\.com|'
                            r'\U0001F916 generated|written by claude|\bclaude-session\b', re.I)
LOCKFILE_OK = ('--frozen-lockfile', '--immutable', 'ci')
GATE_NAMES = ('check:branch', 'branch_gate.py')
BRIEF_GATE_RE = re.compile(r'check:branch|branch_gate\.py|--full\b|--keep-going\b|--time-limit\b', re.I)
JOIN_LINE_RE = re.compile(r'^\s*join\b|\bjoin\.py\b|\bjoin\s+RELEASE-', re.M | re.I)
PC_BOUND_RE = re.compile(r'^\s*PC-bound:\s*\S', re.M | re.I)


class Deny(Exception):
    pass


def deny(reason):
    raise Deny(reason)


def flag(tokens, *names):
    return any(t in names or any(t.startswith(n + '=') for n in names if n.startswith('--')) for t in tokens)


# --- Bash --------------------------------------------------------------------------------

def newest_per_workflow(runs):
    """Only the newest run of each workflow name counts (an older skipped or failed run is superseded)."""
    newest = {}
    for x in runs:
        if not isinstance(x, dict):
            continue
        key = x.get('workflowName') or ''
        rank = (str(x.get('createdAt') or ''), x.get('databaseId') or 0)
        if key not in newest or rank >= newest[key][0]:
            newest[key] = (rank, x)
    return [v[1] for v in newest.values()]


def run_state(root, repo, head):
    """'green' (every run for the head completed successfully), 'none' (no runs), 'pending', 'red';
    None when gh cannot answer. Judges the runs of `repo` itself, not the ledger."""
    r = H.gh(root, ['run', 'list', '--repo', repo, '--commit', head, '--limit', '100',
                    '--json', 'status,conclusion,workflowName,createdAt,databaseId'])
    if not r or r[0] != 0:
        return None
    try:
        runs = json.loads(r[1])
    except ValueError:
        return None
    if not isinstance(runs, list):
        return None
    if not runs:
        return 'none'
    runs = newest_per_workflow(runs)
    if any(x.get('status') != 'completed' for x in runs):
        return 'pending'
    # 'skipped' (e.g. a draft PR skipped the job) is not a failure; failure/cancelled/timed_out still block
    return 'green' if all(x.get('conclusion') in ('success', 'skipped') for x in runs) else 'red'


def check_merge(root, seg, ledger):
    if flag(seg, '--auto'):
        deny('DL-05 gh pr merge --auto is never used. Wait for ci_watch.py to pass for the current head, then run '
             'gh pr merge without --auto.')
    target = H.gh_target(seg)
    arg, repo, number = target['selector'], target['repo'], target['number']
    ref = [arg] if arg else []
    foreign = False
    if repo:
        # the PR lives in -R/--repo (or its URL): judge it by the train that carries that repo; a repo the ledger
        # does not track (another project's) is judged by that repo's own CI runs for the PR head
        carried = [t for t in ledger['trains'] if str(t.get('repo') or '').lower() == repo.lower()]
        here = H.gh(root, ['repo', 'view', '--json', 'nameWithOwner'])
        current = None
        if here and here[0] == 0:
            try:
                current = json.loads(here[1]).get('nameWithOwner')
            except (ValueError, AttributeError):
                pass
        foreign = not carried and bool(current) and current.lower() != repo.lower()
        ref = [str(number)] if number is not None else ref
        ref += ['--repo', repo]
    r = H.gh(root, ['pr', 'view'] + ref + ['--json', 'number,headRefOid'])
    pr_no, head = None, None
    if r and r[0] == 0:
        try:
            j = json.loads(r[1])
            pr_no, head = j.get('number'), j.get('headRefOid')
        except ValueError:
            pass
    if pr_no is None:
        pr_no = number
    if foreign:
        if not head:
            return                               # cannot tell what the PR head is: fail open
        state = run_state(root, repo, head)
        if state is None or state == 'green':
            return
        deny('DL-06 %s PR %s: %s. Wait until every workflow run of its current head (%s) has completed '
             'successfully, then merge.' % (repo, pr_no if pr_no is not None else arg or 'N',
                                            {'none': 'no workflow runs for the current head',
                                             'pending': 'workflow runs for the current head are still pending',
                                             'red': 'a workflow run for the current head failed'}[state], head[:8]))
    trains = [t for t in ledger['trains'] if pr_no is not None and t.get('pr') == pr_no
              and (not repo or not t.get('repo') or str(t['repo']).lower() == repo.lower())]
    ok = [t for t in trains if (t.get('ci') or {}).get('state') == 'success'
          and (head is None or (t.get('ci') or {}).get('head_sha') == head)]
    if not ok:
        deny('DL-06 no ledger CI success for the current head of PR %s. Run ci_watch.py for the head commit '
             '(delivery_ledger records it), then merge.' % (pr_no if pr_no is not None else arg or 'N'))


def check_unfrozen(seg, command, cfg):
    t = [x.lower() for x in H.strip_prefix(seg)]
    if '--no-frozen-lockfile' in t:
        deny('DL-23 never install without a frozen lockfile. If the gate failed at setup, the lockfile is stale '
             '(regenerate it and commit) or the install was killed for memory (exit 137: larger pool cap or fewer parallel jobs).')
    if not t or t[0] not in ('npm', 'pnpm', 'yarn', 'bun'):
        return
    sub = t[1] if len(t) > 1 else ''
    installing = sub in ('install', 'i', 'add') or (t[0] == 'yarn' and len(t) == 1)
    if installing and not any(f in t for f in ('--frozen-lockfile', '--immutable', '--ci')):
        if any(m.lower() in command.lower() for m in cfg['gate_markers']):
            deny('DL-23 no unfrozen install in a gate context. Use npm ci / pnpm install --frozen-lockfile; a stale '
                 'lockfile is regenerated and committed, never installed around; an install killed for memory (exit 137) needs a larger pool cap.')


def check_run_watch(seg):
    """DL-95: `gh run watch` polls every 3 s by default and drains the shared GitHub quota."""
    toks = H.strip_prefix(seg)
    interval = None
    for i, t in enumerate(toks):
        if t in ('--interval', '-i') and i + 1 < len(toks):
            interval = toks[i + 1]
        elif t.startswith('--interval='):
            interval = t.split('=', 1)[1]
    try:
        ok = interval is not None and float(interval) >= 60
    except ValueError:
        ok = False
    if not ok:
        deny('DL-95 never gh run watch without --interval 60 or more (the default 3 s drains the GitHub quota '
             'for every session). Watch CI with ci_watch.py, one watcher for many runs.')


def check_kill(seg, command):
    t = [x.lower() for x in H.strip_prefix(seg)]
    prog = t[0] if t else ''
    msg = ('DL-42 stop only processes and containers you started: kill by the pid or container id you recorded in '
           'the ledger, never by name or all at once.')
    if prog in ('pkill', 'killall'):
        deny(msg)
    if prog == 'taskkill' and any(x in ('/im', '-im') for x in t):
        deny(msg)
    if is_stop_program(t):
        if any('$(' in x or '`' in x for x in t) and re.search(
                r'[$(`]\s*\(?\s*(?:docker\s+(?:ps|container\s+ls)|pgrep)\b', ' '.join(t)):
            deny(msg)
    if prog == 'xargs' and is_stop_program(t[1:]) and re.search(r'docker\s+(?:ps|container\s+ls|ls)\b', command):
        deny(msg)        # `docker ps -q | xargs docker stop`: the list comes from the segment before the pipe


def is_stop_program(t):
    """DL171: the segment stops or kills something: docker stop/kill/rm, docker compose down/stop/kill/rm, kill,
    taskkill, pkill, Stop-Process. A `$(docker ps ...)` inside docker exec, logs, inspect or cp is only a lookup."""
    if not t:
        return False
    if t[0] in ('kill', 'killall', 'pkill', 'taskkill', 'stop-process'):
        return True
    if t[0] != 'docker':
        return False
    rest = [x for x in t[1:] if not x.startswith('-')]
    if rest[:1] in (['stop'], ['kill'], ['rm']):
        return True
    if rest[:2] in (['container', 'stop'], ['container', 'kill'], ['container', 'rm']):
        return True
    return rest[:1] == ['compose'] and rest[1:2] in (['down'], ['stop'], ['kill'], ['rm'])


def norm_path(p):
    """DL133: one form for Windows, Git Bash (/c/x) and WSL (/mnt/c/x) paths: C:/x, lower case, no trailing slash."""
    p = p.replace('\\', '/')
    m = re.match(r'^/(?:mnt/)?([A-Za-z])(?=/|$)', p)
    if m:
        p = m.group(1) + ':' + p[m.end():]
    return os.path.normpath(p).replace('\\', '/').rstrip('/').lower()


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


def current_branch(cwd):
    try:
        r = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=cwd, capture_output=True, text=True,
                           timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def runs_branch_gate(seg):
    """True when the simple command runs the branch gate: pnpm/npm/yarn run check:branch, branch_gate.py, or
    run_suite.py --full."""
    t = H.strip_prefix(seg)
    low = [x.lower() for x in t]
    if any(os.path.basename(x.replace('\\', '/')) == 'branch_gate.py' for x in low):
        return True
    if low and low[0] in ('npm', 'pnpm', 'yarn', 'bun', 'npx') and 'check:branch' in low[1:]:
        return True
    return any(os.path.basename(x.replace('\\', '/')) == 'run_suite.py' for x in low) and '--full' in low


def check_join_gate(seg, cfg, branch):
    """DL-11: the branch gate never runs on a release/integration branch (`branch` is the one in force)."""
    if not runs_branch_gate(seg):
        return
    t = H.strip_prefix(seg)
    for i, x in enumerate(t[:-1]):
        if x == '--head':
            branch = t[i + 1]
    if H.is_release_branch(cfg, branch):
        deny('DL-11 a join is light: typecheck + lint of touched packages and the fast guards (fast_guards.py), then '
             'push and open the ready PR; the ready PR CI is the one full run. Do not run the branch gate on %s.'
             % branch)


def check_bash(root, cfg, ledger, data, at):
    command = (data.get('tool_input') or {}).get('command') or ''
    cwd = data.get('cwd') if isinstance(data.get('cwd'), str) else root
    branch = None            # None: ask git lazily; a `git checkout/switch <ref>` earlier in the command overrides
    for seg in H.segments(command):
        if H.starts_with(seg, ['git', 'checkout']) or H.starts_with(seg, ['git', 'switch']):
            refs = [a for a in H.strip_prefix(seg)[2:] if not a.startswith('-')]
            if refs:
                branch = refs[-1]
        if H.check_on(cfg, 'DL-11') and runs_branch_gate(seg):
            check_join_gate(seg, cfg, branch if branch is not None else current_branch(cwd))
        if H.starts_with(seg, ['gh', 'pr', 'merge']) and H.check_on(cfg, 'DL-05'):
            check_merge(root, seg, ledger)
        if H.starts_with(seg, ['gh', 'pr', 'checks']) and flag(seg, '--watch') and H.check_on(cfg, 'DL-07'):
            deny('DL-07 do not watch the PR check list. Watch the workflow runs of the head commit: ci_watch.py <sha>.')
        if H.starts_with(seg, ['gh', 'run', 'watch']) and H.check_on(cfg, 'DL-95'):
            check_run_watch(seg)
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

def _fetch_checker():
    """DL-94: load workflow_fetch_check.py from the plugin's own templates (one copy, no second one to drift)."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, '..', 'templates', 'shared', 'scripts', 'delivery', 'workflow_fetch_check.py')
    spec = importlib.util.spec_from_file_location('workflow_fetch_check', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_workflow_fetch(root, cfg, data):
    """DL-94: a write to .github/workflows/ must not add an uncached, unchecked tool download. Fails open."""
    try:
        if not H.check_on(cfg, 'DL-94'):
            return
        ti = data.get('tool_input') or {}
        path = ti.get('file_path') or ''
        full = os.path.abspath(path if os.path.isabs(path) else os.path.join(root, path))
        rel = os.path.relpath(full, root).replace('\\', '/')
        if not rel.startswith('.github/workflows/') or not rel.lower().endswith(('.yml', '.yaml')):
            return
        if data.get('tool_name') == 'Write':
            texts = [ti.get('content')]
        elif data.get('tool_name') == 'MultiEdit':
            texts = [e.get('new_string') for e in (ti.get('edits') or []) if isinstance(e, dict)]
        else:
            texts = [ti.get('new_string')]
        found = []
        mod = _fetch_checker()
        for t in texts:
            if isinstance(t, str):
                found += mod.check_text(t, rel)
    except Exception:       # fail open
        return
    if found:
        deny('DL-94 %s Fetch pinned tools through the per-runner cache: '
             'python3 scripts/delivery/ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>. '
             'A reviewed exception ends the line with "# ci-tool: ok <reason>".' % ' | '.join(found[:5]))


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


def cloud_create_connectors_ok(ti):
    """DL-93: a cloud create names its connectors. True when the body sets clear_mcp_connections: true, or lists
    connectors in mcp_connections (the brief needs them). Without either the account's connectors attach."""
    body = ti.get('body')
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            body = {}
    pairs = list(walk(body if isinstance(body, (dict, list)) else {}))
    if any(k == 'clear_mcp_connections' and v is True for k, v in pairs):
        return True
    return any(k == 'mcp_connections' and isinstance(v, list) and v for k, v in pairs)


E2E_BRIEF_MARKER = ('e2e specs', 'no ui change')   # DL-89: any one in the brief satisfies the check


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
                out['owns'] += split_owns(kv.group(2).strip('[]'))
            else:
                out[key] = kv.group(2)
    return out


def split_owns(text):
    """Split an owns list on commas outside parentheses (DL158)."""
    out, depth, cur = [], 0, ''
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')' and depth:
            depth -= 1
        if ch == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += ch
    out.append(cur)
    return [x.strip().strip('\'"') for x in out if x.strip()]


NOTE_RE = re.compile(r'^(.*?)\s*\(([^()]*)\)\s*$')
REQ_RE = re.compile(r'\bR\d+\.\d+\b')


def owns_entry(raw):
    """(path, note) of one owns entry. path is None for prose (no '/' and no '.')."""
    m = NOTE_RE.match(raw.strip())
    path, note = (m.group(1), m.group(2)) if m else (raw.strip(), '')
    path = path.strip().replace('\\', '/')
    while path.startswith('./'):
        path = path[2:]
    if ' ' in path or not ('/' in path or '.' in path):
        return None, note
    return path, note


def own_segments(path):
    """Segments of a path; a plain directory entry (no wildcard, no extension, or ending in '/') owns all under it."""
    segs = [x for x in path.split('/') if x]
    last = segs[-1] if segs else ''
    if path.endswith('/') or not (re.search(r'[*?\[]', last) or '.' in last):
        segs.append('**')
    return segs


def match_segs(a, b):
    if not a or not b:
        return all(x == '**' for x in (a or b))
    if a[0] == '**':
        return match_segs(a[1:], b) or match_segs(a, b[1:])
    if b[0] == '**':
        return match_segs(a, b[1:]) or match_segs(a[1:], b)
    if a[0] == b[0] or fnmatch.fnmatchcase(a[0], b[0]) or fnmatch.fnmatchcase(b[0], a[0]):
        return match_segs(a[1:], b[1:])
    return False


def overlap_info(a, b):
    """None when the entries cannot match one path; else a message part naming both notes (DL158)."""
    pa, na = owns_entry(a)
    pb, nb = owns_entry(b)
    if pa is None or pb is None or not match_segs(own_segments(pa), own_segments(pb)):
        return None
    ra, rb = set(REQ_RE.findall(na)), set(REQ_RE.findall(nb))
    if pa == pb and ra and rb and not (ra & rb) and 'only' in na.lower() and 'only' in nb.lower():
        return None
    return 'notes: "%s" / "%s"' % (na or 'none', nb or 'none')


def overlaps(a, b):
    return overlap_info(a, b) is not None


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


def check_join_brief(cfg, text, block):
    """DL-11: a join brief never names the branch gate. A join brief is one whose delivery block branch is a
    release/integration branch, or whose text mentions join.py, has a line starting 'Join', or says 'join RELEASE-'."""
    is_join = H.is_release_branch(cfg, (block.get('branch') or '').strip()) or bool(JOIN_LINE_RE.search(text))
    named = BRIEF_GATE_RE.search(text) if is_join else None
    if named:
        deny('DL-11 a join is light, so this join brief must not name the branch gate (found "%s"). Brief the light '
             'steps instead: merge, resolve conflicts, fold spec notes, typecheck + lint of touched packages, fast '
             'guards (fast_guards.py), push, open the ready PR; its CI is the one full run.' % named.group(0))


ETA_LINE_RE = re.compile(r'^\s*eta\s*:\s*(.+)$', re.M | re.I)
ETA_REASON_RE = re.compile(r'^\s*eta-reason\s*:\s*\S', re.M | re.I)
ETA_MIN_SAMPLES = 5
ETA_SLACK = 1.5


def eta_total_min(text):
    """Minutes of the brief's `eta:` line: the number after '=', else the sum of its 'word N' parts; None if none."""
    m = ETA_LINE_RE.search(text)
    if not m:
        return None
    line = m.group(1)
    tot = re.search(r'=\s*(\d+(?:\.\d+)?)\s*min', line)
    if tot:
        return float(tot.group(1))
    parts = re.findall(r'[A-Za-z]+\s+(\d+(?:\.\d+)?)', line.split('(')[0])
    return float(sum(float(x) for x in parts)) if parts else None


def check_eta_measured(ledger, text, where):
    """DL-30 (DL168): an agent ETA more than 50 % above the measured p75 needs a lower eta or an eta-reason line."""
    total = eta_total_min(text)
    if total is None or ETA_REASON_RE.search(text):
        return
    try:
        import delivery_eta as E
        est = E.estimate_ledger(ledger, 'agent', where)
    except Exception:  # noqa: BLE001 - fail open
        return
    if est['n'] < ETA_MIN_SAMPLES or est['p75'] is None or total <= est['p75'] * ETA_SLACK:
        return
    deny('DL-30 the brief eta is %g min, but %d %s agents took a median of %g min (p75 %g min). Do not pad: lower the '
         'eta, or add a line "eta-reason: <why this one is longer>" in the delivery block.'
         % (total, est['n'], where, est['median'], est['p75']))


def check_launch(cfg, ledger, data, where):
    ti = data.get('tool_input') or {}
    if where == 'cloud':
        action = str(ti.get('action') or '').lower()
        if action not in ('create', 'run') or not isinstance(ti.get('body') or ti.get('prompt'), (dict, str)):  # update, list, get, list_runs, get_run_log and a bare run of a stored trigger are not launches
            return
    if where == 'cloud' and action == 'create' and H.check_on(cfg, 'DL-93') and not cloud_create_connectors_ok(ti):
        deny('DL-93 this create body would attach all of the account\'s connectors. Set "mcp_connections": [] and '
             '"clear_mcp_connections": true in the body (or list the connectors the brief needs in mcp_connections), '
             'then create the routine.')
    text = brief_text(ti)
    block = delivery_block(text)
    if H.check_on(cfg, 'DL-11'):
        check_join_brief(cfg, text, block)
    if H.check_on(cfg, 'DL-30'):
        check_eta_measured(ledger, text, where)
    cloud_running = len(H.running_agents(ledger, 'cloud'))
    local_running = len(H.running_agents(ledger, 'local'))
    caps = cfg['caps']
    cap_cloud, cap_local = int(caps.get('cloud', 50)), int(caps.get('local', 3))
    cap_total = int(caps.get('total', cap_cloud + cap_local))
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
    # A marker is a string, or a list of strings of which any one satisfies it (DL-36: a project on the CI-gate
    # path accepts "CI is the gate" where another says "one affected gate").
    low = text.lower()
    missing = [' / '.join(m) if isinstance(m, list) else m for m in cfg['brief_markers']
               if not any(str(x).lower() in low for x in (m if isinstance(m, list) else [m]))]
    # DL-89: every cloud brief says the agent runs the e2e specs of the screens it changes (or that it changes no UI).
    if H.check_on(cfg, 'DL-89') and not any(str(x).lower() in low for x in E2E_BRIEF_MARKER):
        deny('DL-89 the brief must say the agent runs the e2e specs of the screens it changes before CODE DONE '
             '("run the e2e specs of the screens you change"), or that it changes no UI ("no UI change"). '
             'The template line is in references/agent-brief-template.md. Add it, then launch.')
    if missing and H.check_on(cfg, 'DL-36'):
        deny('DL-36 the brief lacks required markers: %s. Add them (config brief_markers), then launch.'
             % '; '.join(missing))
    if H.check_on(cfg, 'DL-38'):
        if cloud_running + local_running >= cap_total:
            deny('DL-38 total cap reached (%d running of %d). Wait for one to finish.' % (cloud_running + local_running, cap_total))
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
                    info = overlap_info(mine, theirs) if isinstance(theirs, str) else None
                    if info:
                        deny('DL-41 files "%s" overlap "%s" owned by running agent %s (%s). Split by file ownership or '
                             'wait for that agent to finish.' % (mine, theirs, a.get('task') or a.get('id'), info))


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


def check_postpone(ledger, data, at):
    """DL136: a warning (never a block) when a routine is set to run within 2 hours while a question is open."""
    ti = data.get('tool_input') or {}
    if str(ti.get('action') or '').lower() not in ('create', 'update'):
        return None
    raw = find_key(ti, 'run_once_at')
    when = H.parse_ts(raw) if isinstance(raw, str) else None
    if when is None:
        return None
    mins = H.minutes_since(raw, at)
    if mins is None or mins >= 0 or -mins >= 120:     # in the past (a run now) or 2 hours or more away: fine
        return None
    open_q = [q for q in ledger.get('owner_questions') or [] if isinstance(q, dict) and not q.get('answered_at')]
    if not open_q:
        return None
    return ('DL136 a question to the owner is open and this routine runs in %d min. A routine held for an owner '
            'answer is paused (no run_once_at in the near future), never postponed by minutes: it would start on '
            'its old brief if the dialog stays open.' % round(-mins))


def check_trickle(cfg, ledger, data, at):
    """Q-5: no second question batch while this session's agents still run (park it until the wave reports)."""
    sid = data.get('session_id')
    mine = [a for a in H.running_agents(ledger) if not sid or not a.get('launched_by') or a.get('launched_by') == sid]
    if not mine or all(a.get('blocked_on') == 'owner' for a in mine):
        return
    prompt = ledger.get('owner_prompt') if isinstance(ledger.get('owner_prompt'), dict) else {}
    if prompt.get('asked_for_questions'):
        return
    since = H.parse_ts(prompt.get('at'))
    window = float(cfg['question_window_min'])
    batch = float(cfg['question_batch_sec']) / 60.0
    recent = []
    for q in ledger['owner_questions']:
        asked = H.parse_ts(q.get('asked_at'))
        if asked is None or (since is not None and asked < since):
            continue
        age = H.minutes_since(q.get('asked_at'), at)
        if age is not None and age <= window:
            recent.append(age)
    # dialogs of one message arrive seconds apart (Q-1): only a batch older than that makes this a trickle
    if recent and min(recent) > batch:
        deny('Q-5 you already asked the owner a question batch %d min ago and %d agent(s) of this session are still '
             'running (%s). Park the question until the running agents of this wave report, then ask everything at '
             'once. Allowed when every running agent is blocked on the answer, or when the owner asked you to ask '
             'questions.' % (round(min(recent)), len(mine), ', '.join(str(a.get('task') or a.get('id')) for a in mine[:3])))


def main():
    if H.hooks_off():
        return 0
    data = H.read_input()
    root = H.find_root(data)
    # DL-77: the load guard protects the machine, so it runs in every project, with or without .delivery/
    ledger0 = H.load_ledger(root) if root else None
    held = G.check_call(data, G.project_cfg(root), ledger0, local=False)
    if held:
        if root and H.C.enforcement(H.load_config(root))['mode'] == 'warn':
            print(json.dumps({'systemMessage': 'luismc-delivery (warn mode, call allowed): ' + held}))
        else:
            if root:
                H.log_block(root, H.load_config(root), 'pre-tool', held)
            print(held, file=sys.stderr)
            return 2
    if not root:
        held = G.check_local(data, G.project_cfg(root), ledger0)
        if held:
            print(held, file=sys.stderr)
            return 2
        G.heavy_begin(data, G.project_cfg(root))
        return 0
    cfg = H.load_config(root)
    ledger = ledger0
    at = H.now()
    tool = data.get('tool_name')
    denied = False
    try:
        if tool in ('Bash', 'PowerShell'):
            check_bash(root, cfg, ledger, data, at)
        elif tool == 'Write':
            check_workflow_fetch(root, cfg, data)
            check_write(root, cfg, data)
        elif tool in ('Edit', 'MultiEdit'):
            check_workflow_fetch(root, cfg, data)
        elif tool == 'Agent':
            check_launch(cfg, ledger, data, 'local')
        elif tool == 'RemoteTrigger':
            check_launch(cfg, ledger, data, 'cloud')
            note = check_postpone(ledger, data, at)
            if note:
                print(json.dumps({'systemMessage': 'luismc-delivery (warning, call allowed): ' + note}))
        elif tool == 'AskUserQuestion':
            check_question(cfg, ledger, data, at)
            if H.check_on(cfg, 'Q-5'):
                check_trickle(cfg, ledger, data, at)
    except Deny as d:
        if H.C.enforcement(cfg)['mode'] == 'warn':      # enforcement.mode warn: say it, let the call through
            print(json.dumps({'systemMessage': 'luismc-delivery (warn mode, call allowed): ' + str(d)}))
        else:
            denied = True
            H.log_block(root, cfg, 'pre-tool', str(d))
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                     'permissionDecisionReason': str(d)}}))
    if not denied:
        held = G.check_local(data, G.project_cfg(root), ledger)   # DL-91 last: a project rule's refusal is more specific
        if held:
            if H.C.enforcement(cfg)['mode'] == 'warn':
                print(json.dumps({'systemMessage': 'luismc-delivery (warn mode, call allowed): ' + held}))
            else:
                H.log_block(root, cfg, 'pre-tool', held)
                print(held, file=sys.stderr)
                return 2
        G.heavy_begin(data, cfg)                         # DL-91: counted until its PostToolUse
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # fail open
        H.warn('pre-tool hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
