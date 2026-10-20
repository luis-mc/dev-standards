"""Shared helpers for the luismc-delivery hooks (DELIVERYSPEC sections 2 and 5).

Config (.delivery/config.json with safe defaults), a read-only adapter over
.delivery/ledger.json (schema 1; written only by delivery_ledger.py, never here), time
helpers, command tokenising and the per-session block state (block once per fingerprint,
3-block ceiling, the pattern of the artifacts plugin R8.4). A project without a
.delivery/ folder is not opted in: every hook returns without output.

Enforcement (config `enforcement`, see delivery_config.py): `mode` block|warn, `block_ceiling` (how often the
same findings block a session, default 3) and `log_every_block` (every block is appended to
.delivery/blocks.log: time, hook, rule id, message).

Seams for tests: DELIVERY_NOW (ISO time), DELIVERY_GH (gh replacement), DELIVERY_FREE_GB.
Disable: CLAUDE_DELIVERY_HOOKS=off. Standard library only.
"""
import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import delivery_config as C   # noqa: E402  (same folder; the hook scripts put it on sys.path)

DISABLE_VALUES = {'off', '0', 'false', 'no'}
BLOCK_LIMIT = 3               # default of enforcement.block_ceiling
BLOCK_LOG_REL = os.path.join('.delivery', 'blocks.log')
RULE_ID_RE = re.compile(r'^(DL-\d+|Q-\d+|D\d+[a-z]?)\b')
STATE_REL = os.path.join('.delivery', 'hook-state.json')
MAX_SESSIONS = 40

DEFAULTS = {
    'tz': 'Europe/Lisbon',
    'work_root': None,                        # DL-53; unset = not checked
    'caps': {'cloud': 8, 'local': 3},         # DL-38
    'min_free_gb': 8,                         # DL-38 local agents need more free memory than this
    'brief_markers': [],                      # DL-36 strings every cloud brief must contain
    'min_question_chars': 60,                 # D8 Q-3
    'question_window_min': 60,                # D8 Q-5 minutes a question batch stays 'recent' while agents run
    'question_batch_sec': 90,                 # D8 Q-1 dialogs this close together are one message
    'send_deny': ['gh issue comment', 'gh issue create', 'gh pr comment', 'gh pr review',
                  'sendmail', 'mutt', 'mailx'],       # DL-73
    'no_attribution': False,                  # DL-74
    'train_label_re': r'\b(?:T-\d{4}-\d{2}-\d{2}-\d+|train[- ]?[A-Za-z0-9]+|release/\d+)\b',   # DL-64
    'gate_markers': ['gate', 'join.py', 'ci_watch'],      # DL-23 commands that count as gate context
    'md_allow': [],                           # DL-75 extra allowed globs
    'registry_open': ['Running', 'Waiting', 'Needs you', 'To do'],    # DL-63
    'join_push_min': 5,                       # DL-02
    'check_min': 30,                          # DL-32
    'watcher_min': 20,                        # DL-33
    'install_stale_min': 90,                  # DL-55 an install older than this no longer blocks
    'pr_proven_jobs': [],                     # DL-76 job names (globs ok) that must not re-run on the default branch
    'checks_off': [],                         # ids switched off, e.g. ["DL-64"]
}
TERMINAL_TRAIN = ('cleaned', 'abandoned')
TERMINAL_AGENT = ('done', 'empty', 'failed', 'stopped')


def hooks_off():
    return os.environ.get('CLAUDE_DELIVERY_HOOKS', 'on').strip().lower() in DISABLE_VALUES


def warn(message):
    try:
        print('luismc-delivery: ' + message.replace('\n', ' '), file=sys.stderr)
    except Exception:
        pass


def read_input():
    try:
        text = sys.stdin.buffer.read().decode('utf-8', 'replace')
        data = json.loads(text) if text.strip() else {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def find_root(data):
    """The nearest directory at or above the input's cwd (else ours) that holds .delivery/; None when the
    project did not opt in."""
    cwd = data.get('cwd') if isinstance(data.get('cwd'), str) else None
    d = os.path.abspath(cwd if cwd and os.path.isdir(cwd) else os.getcwd())
    while True:
        if os.path.isdir(os.path.join(d, '.delivery')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            value = json.load(f)
    except (OSError, ValueError):
        return None
    return value


def load_config(root):
    cfg = copy.deepcopy(DEFAULTS)
    user = read_json(os.path.join(root, '.delivery', 'config.json'))
    if isinstance(user, dict):
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def check_on(cfg, check_id):
    return check_id not in (cfg.get('checks_off') or [])


# --- ledger adapter (read-only; schema 1) -------------------------------------------------

def load_ledger(root):
    """The ledger as a dict with every list present; empty lists when missing or unreadable."""
    raw = read_json(os.path.join(root, '.delivery', 'ledger.json'))
    ledger = raw if isinstance(raw, dict) else {}
    for key in ('trains', 'agents', 'jobs', 'installs', 'publishes', 'runners', 'watchers', 'owner_questions',
                'events'):
        v = ledger.get(key)
        ledger[key] = [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []
    return ledger


def now():
    override = os.environ.get('DELIVERY_NOW')
    if override:
        t = parse_ts(override)
        if t:
            return t
    return datetime.now(timezone.utc)


def parse_ts(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace('Z', '+00:00')
    try:
        t = datetime.fromisoformat(text)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def minutes_since(value, at):
    t = parse_ts(value)
    return None if t is None else (at - t).total_seconds() / 60.0


def on_hold(train, at):
    h = train.get('hold')
    if not h:
        return False
    if isinstance(h, dict):
        until = parse_ts(h.get('until'))
        if until is not None and until <= at:
            return False
    return True


def release_name(train):
    n = train.get('release_no')
    return 'RELEASE-%s' % n if n is not None else 'the train'


def trains_green_unmerged(ledger, at):
    return [t for t in ledger['trains']
            if t.get('green_at') and not t.get('merged_at') and t.get('state') in ('green', 'ci', 'pushed', None)
            and not on_hold(t, at)]


def trains_joined_unpushed(ledger, at, grace_min):
    """Joined trains not pushed while an earlier train went green more than grace_min ago (DL-02)."""
    out = []
    for t in ledger['trains']:
        if t.get('state') != 'joined' or t.get('pushed_at') or on_hold(t, at):
            continue
        for p in ledger['trains']:
            if p is t or p.get('state') == 'abandoned' or not p.get('green_at'):
                continue
            if (p.get('release_no') is not None and t.get('release_no') is not None
                    and p['release_no'] >= t['release_no']):
                continue
            age = minutes_since(p['green_at'], at)
            if age is not None and age > grace_min:
                out.append(t)
                break
    return out


def running_agents(ledger, where=None):
    return [a for a in ledger['agents'] if a.get('state') in ('queued', 'running')
            and (where is None or a.get('where') == where)]


# --- commands -------------------------------------------------------------------------------

def segments(command):
    """Token lists of the simple commands in a shell line (split on ; & | and newlines). Quoted text stays one
    token, so a commit message or an echo never matches a command pattern."""
    out = []
    for line in (command or '').splitlines() or ['']:
        try:
            # non-posix keeps backslashes (Windows paths); matching outer quotes are stripped per token
            lex = shlex.shlex(line, posix=False, punctuation_chars=';&|')
            lex.whitespace_split = True
            toks = [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in '"\'' else t for t in lex]
        except ValueError:
            toks = line.split()
        cur = []
        for tok in toks:
            if tok and set(tok) <= set(';&|'):
                if cur:
                    out.append(cur)
                cur = []
            else:
                cur.append(tok)
        if cur:
            out.append(cur)
    return out


def strip_prefix(tokens):
    """Drop env assignments, sudo, env and a path prefix of the program: ['VAR=1', '/usr/bin/gh', ...]."""
    i = 0
    while i < len(tokens) and (re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', tokens[i]) or tokens[i] in ('sudo', 'env', 'command')):
        i += 1
    rest = list(tokens[i:])
    if rest:
        base = os.path.basename(rest[0].replace('\\', '/'))
        rest[0] = re.sub(r'\.(exe|cmd|bat)$', '', base, flags=re.I)
    return rest


def starts_with(tokens, words):
    t = strip_prefix(tokens)
    return len(t) >= len(words) and [x.lower() for x in t[:len(words)]] == [w.lower() for w in words]


def gh(root, args, timeout=20):
    """(rc, stdout) of gh (or DELIVERY_GH); None when it cannot run."""
    prog = os.environ.get('DELIVERY_GH')
    argv = ([sys.executable, prog] if prog and prog.endswith('.py') else [prog] if prog else ['gh']) + list(args)
    try:
        p = subprocess.run(argv, cwd=root, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.returncode, p.stdout.decode('utf-8', 'replace')


# --- per-session block state (artifacts R8.4 pattern) ---------------------------------------

def repeat_limit(cfg, default=3):
    """stop_repeat_limit: how many turn ends the same unchanged finding may block; 0 = never limit.
    Unset, it follows enforcement.block_ceiling (passed as `default`)."""
    v = cfg.get('stop_repeat_limit')
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else default


def fingerprint(keys):
    return hashlib.sha256(json.dumps(sorted(keys)).encode('utf-8')).hexdigest()[:16]


def read_state(root):
    s = read_json(os.path.join(root, STATE_REL))
    return s if isinstance(s, dict) else {}


def write_state(root, state):
    path = os.path.join(root, STATE_REL)
    while len(state) > MAX_SESSIONS:
        state.pop(next(iter(state)))
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except OSError as exc:
        warn('state not written (%s)' % exc)


def rule_id(message):
    """The DL/Q/D id a finding or denial starts with ('DL-31 the reply ...'); 'other' when it has none."""
    m = RULE_ID_RE.match((message or '').strip())
    return m.group(1) if m else 'other'


def log_block(root, cfg, hook, message):
    """enforcement.log_every_block: append `time<TAB>hook<TAB>rule<TAB>message` to .delivery/blocks.log (for the
    owner's review). Never raises."""
    if not C.enforcement(cfg)['log_every_block']:
        return
    line = '\t'.join([now().strftime('%Y-%m-%dT%H:%M:%SZ'), hook, rule_id(message),
                      ' '.join(str(message).split())])
    try:
        with open(os.path.join(root, BLOCK_LOG_REL), 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError as exc:
        warn('blocks.log not written (%s)' % exc)


def block_decision(root, sid, keys, ceiling=None):
    """('block'|'release'|'clear', blocks_so_far). Same fingerprint blocks up to `ceiling` (enforcement.block_ceiling,
    default BLOCK_LIMIT) times, then lets the turn end; a changed fingerprint starts again."""
    ceiling = BLOCK_LIMIT if ceiling is None else ceiling
    state = read_state(root)
    if not keys:
        if sid in state:
            del state[sid]
            write_state(root, state)
        return 'clear', 0
    digest = fingerprint(keys)
    entry = state.get(sid) if isinstance(state.get(sid), dict) else {}
    blocks = entry.get('blocks', 0) if entry.get('last') == digest else 0
    if not isinstance(blocks, int):
        blocks = 0
    if blocks >= ceiling:
        return 'release', blocks
    state.pop(sid, None)
    state[sid] = {'blocks': blocks + 1, 'last': digest}
    write_state(root, state)
    return 'block', blocks + 1
