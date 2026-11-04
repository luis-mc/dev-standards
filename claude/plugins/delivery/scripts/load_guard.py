"""Load guard decisions (DELIVERYSPEC DL-77, DL-78): is this tool call heavy, and is the machine over its limits?

Used by hook_pre_tool.py (refuses new heavy work with exit 2), hook_stop.py and hook_session_start.py (a non-blocking
notice). The guard only HOLDS NEW work: it never kills, suspends or lowers the priority of anything. It is on in every
project where the plugin is enabled, with or without .delivery/ (it protects the machine, not the project).

Heavy (DL-77): test runners (vitest, jest, pytest, playwright, mocha, `python -m pytest|unittest`), package-manager
scripts named test, e2e, check* or build* (`pnpm test`, `pnpm check:branch`, `npm run build`, also via run/exec/dlx),
turbo/nx runs, `tsc -b`, next/vite/webpack builds, cargo/dotnet/go/gradle/mvn builds and tests, msbuild, docker build
and compose up/build, ffmpeg, installs (`pnpm|npm|yarn|bun install|add|ci` unless `--offline`: an install unpacks
thousands of files and was the crash trigger of 23 Oct), anything started in the background that is not plainly light
(`run_in_background`, trailing `&`, nohup, Start-Process), and any command matching a `heavy_commands` regex. A local
Agent launch (no remote/cloud isolation) and a Workflow are heavy. RemoteTrigger and Agent with isolation remote/cloud
run elsewhere and are never refused. Everything else (git, gh, ls, cat, grep, rtk-wrapped reads, python one-liners) is
light and never refused.

Local heavy limit (DL-91, D36): at most `local_heavy` (machine config, default 2; a project may lower it) heavy calls run
at once on this machine, across sessions. A heavy foreground command (Bash, PowerShell, Workflow) is counted from its
PreToolUse to its PostToolUse (a small file per call in the local-heavy folder, see heavy_dir); a local agent is counted
from the delivery ledger. At the limit a new heavy call is refused with the list of what runs. Local work does not take
CI slots (D23); the load check above covers both.
"""
import copy
import hashlib
import io
import json
import os
import re
import sys
import time
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooklib as H  # noqa: E402
import load as L  # noqa: E402
import machine_slots as MS  # noqa: E402

CHECK_ID = 'DL-77'
LOCAL_CHECK_ID = 'DL-91'
SHELL_TOOLS = ('Bash', 'PowerShell')
GUARDED_TOOLS = SHELL_TOOLS + ('Agent', 'Workflow')
TRACKED_TOOLS = SHELL_TOOLS + ('Workflow',)   # DL-91: counted from PreToolUse to PostToolUse (agents: the ledger)

RUNNERS = {'vitest', 'jest', 'pytest', 'py.test', 'playwright', 'mocha', 'cypress', 'ffmpeg', 'msbuild', 'turbo',
           'nx', 'xcodebuild', 'gradle', 'gradlew', 'tox', 'nox'}
PKG = {'pnpm', 'npm', 'yarn', 'bun'}
PKG_RUN = {'run', 'run-script', 'exec', 'dlx', 'x', 'npx'}
SCRIPT_RE = re.compile(r'^(test|e2e|check|build)([:\-._].*)?$', re.I)
INSTALL_SUBS = {'install', 'i', 'add', 'ci'}
BUILD_TOOLS = {                              # program -> subcommands that are heavy
    'cargo': {'build', 'test', 'check', 'clippy', 'bench', 'run'},
    'dotnet': {'build', 'test', 'publish', 'pack'},
    'go': {'build', 'test'},
    'mvn': {'compile', 'package', 'verify', 'install', 'test'},
    'make': set(),
}
WRAPPERS = {'rtk', 'time', 'nice', 'nohup', 'npx', 'sudo', 'env', 'command', 'call'}
LIGHT = {'git', 'gh', 'ls', 'dir', 'cat', 'head', 'tail', 'grep', 'rg', 'find', 'echo', 'pwd', 'cd', 'wc', 'sed',
         'awk', 'jq', 'cp', 'mv', 'mkdir', 'rm', 'touch', 'type', 'date', 'which', 'where', 'curl',
         'get-content', 'select-string', 'get-childitem', 'write-output', 'set-location'}
BG_RE = re.compile(r'(?<!&)&\s*$|\bnohup\b|\bstart-process\b|\bstart\s+/b\b', re.I)


def _program(tokens):
    """(program, rest) after env assignments, sudo/env and wrappers like rtk, nohup, npx."""
    t = H.strip_prefix(tokens)
    while t and t[0].lower() in WRAPPERS:
        t = H.strip_prefix(t[1:])
    if t and t[0].lower() in ('cmd', 'cmd.exe') and len(t) > 2 and t[1].lower() in ('/c', '/k'):
        t = H.strip_prefix(t[2:])
    if t and t[0].lower() in ('powershell', 'pwsh') and '-command' in [x.lower() for x in t[1:]]:
        i = [x.lower() for x in t].index('-command')
        t = H.strip_prefix(t[i + 1:])
    return (t[0].lower(), t[1:]) if t else ('', [])


def _subcommand(rest):
    """First non-option token and what follows it (pnpm --filter x test: the option value is skipped for known flags)."""
    skip = False
    for i, x in enumerate(rest):
        if skip:
            skip = False
            continue
        if x in ('--filter', '-F', '--dir', '-C', '--prefix', '-w', '--workspace', '--cwd'):
            skip = True
            continue
        if not x.startswith('-'):
            return x.lower(), rest[i + 1:]
    return '', []


def _segment_heavy(tokens):
    """The reason a simple command is heavy, or None."""
    prog, rest = _program(tokens)
    if not prog:
        return None
    flags = [x.lower() for x in rest]
    if prog in RUNNERS:
        return prog
    if prog in ('python', 'python3', 'py') and '-m' in flags:
        mod = flags[flags.index('-m') + 1] if flags.index('-m') + 1 < len(flags) else ''
        if mod in ('pytest', 'unittest', 'tox', 'nox'):
            return 'python -m ' + mod
    if prog == 'tsc' and ('-b' in flags or '--build' in flags):
        return 'tsc -b'
    if prog in ('next', 'vite', 'webpack', 'rollup', 'esbuild', 'nuxt', 'astro', 'turbo') and \
            (prog == 'webpack' or (flags and flags[0] in ('build', 'run', 'export'))):
        return prog + ' ' + (flags[0] if flags and prog != 'webpack' else 'build')
    if prog in PKG:
        sub, after = _subcommand(rest)
        if sub in PKG_RUN:
            sub = (after[0].lower() if after else '')
            if sub in RUNNERS or sub in ('vitest', 'jest', 'playwright', 'tsc'):
                return '%s %s' % (prog, sub)
            if sub == 'turbo' or sub == 'nx':
                return '%s %s' % (prog, sub)
        if SCRIPT_RE.match(sub):
            return '%s %s' % (prog, sub)
        if sub in INSTALL_SUBS and '--offline' not in flags:
            return '%s %s' % (prog, sub)
        return None
    if prog in BUILD_TOOLS:
        sub, _ = _subcommand(rest)
        if sub in BUILD_TOOLS[prog] or (prog == 'make' and not sub):
            return '%s %s' % (prog, sub)
    if prog in ('gradle', 'gradlew', './gradlew'):
        return prog
    if prog == 'docker' or prog in ('docker-compose',):
        sub, after = _subcommand(rest)
        if prog == 'docker' and sub == 'compose':
            sub = (_subcommand(after)[0])
        if sub in ('build', 'buildx', 'up'):
            return 'docker ' + sub
    return None


def _all_light(segs):
    for s in segs:
        prog, _ = _program(s)
        if prog not in LIGHT and 'delivery_' not in ' '.join(s).lower() and 'ci_watch' not in ' '.join(s).lower():
            return False
    return bool(segs)


def classify(tool, tool_input, cfg=None):
    """(heavy, label): label names the command class for the refusal message. Never raises on odd input."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    cfg = cfg or {}
    if tool == 'Workflow':
        return True, 'a Workflow (runs several local agents)'
    if tool == 'Agent':
        iso = str(ti.get('isolation') or '').lower()
        if iso in ('remote', 'cloud'):
            return False, 'cloud agent'
        return True, 'a local Agent launch'
    if tool not in SHELL_TOOLS:
        return False, ''
    command = ti.get('command') if isinstance(ti.get('command'), str) else ''
    segs = H.segments(command)
    for s in segs:
        why = _segment_heavy(s)
        if why:
            return True, why
    for pattern in cfg.get('heavy_commands') or []:
        try:
            if re.search(pattern, command, re.I):
                return True, 'a command matching heavy_commands /%s/' % pattern
        except re.error:                      # not a regex: plain command text ("pnpm test:full") matches as a substring
            if isinstance(pattern, str) and pattern.lower() in command.lower():
                return True, 'a command listed in heavy_commands'
        except TypeError:
            continue
    background = ti.get('run_in_background') is True or bool(BG_RE.search(command))
    if background and not _all_light(segs):
        return True, 'a background job'
    return False, ''


# --- local heavy work in flight (DL-91) --------------------------------------------------------

def heavy_dir():
    """Where in-flight heavy calls are kept: DELIVERY_LOCAL_HEAVY_DIR, else local-heavy in the machine folder when that
    can be written, else ~/.claude/luismc-delivery-local-heavy."""
    env = os.environ.get('DELIVERY_LOCAL_HEAVY_DIR')
    if env:
        return env
    mdir = MS.machine_dir()
    if os.path.isdir(mdir) and os.access(mdir, os.W_OK):
        return os.path.join(mdir, 'local-heavy')
    return os.path.join(os.path.expanduser('~'), '.claude', 'luismc-delivery-local-heavy')


def _heavy_key(data):
    ti = data.get('tool_input') if isinstance(data.get('tool_input'), dict) else {}
    raw = data.get('tool_use_id')
    if isinstance(raw, str) and re.fullmatch(r'[\w.\-]{1,100}', raw):
        return raw
    text = '%s|%s|%s' % (data.get('session_id'), data.get('tool_name'), json.dumps(ti, sort_keys=True))
    return hashlib.sha1(text.encode('utf-8', 'replace')).hexdigest()[:20]


def heavy_running(cfg=None, now=None):
    """The foreground heavy calls in flight: [{'key', 'label', 'at'}]. An entry whose process is gone (same host), or
    older than slot_stale_min, is dropped (a record with no pid, as heavy_begin writes, is kept until heavy_end or then)."""
    now = time.time() if now is None else now
    stale = MS.machine_config()['slot_stale_min'] * 60
    out = []
    folder = heavy_dir()
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for name in names:
        if not name.endswith('.json'):
            continue
        path = os.path.join(folder, name)
        rec = MS._read_json(path)
        if rec is None:
            continue
        if MS._holder_gone(rec) or now - (rec.get('ts') or now) > stale:
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        out.append({'key': name[:-5], 'label': rec.get('label') or '?', 'at': rec.get('ts')})
    return out


def heavy_begin(data, cfg=None):
    """Count this call as heavy work in flight (PreToolUse, after the call is allowed). No-op for a light call. Never
    raises."""
    try:
        tool = data.get('tool_name')
        if tool not in TRACKED_TOOLS or not H.check_on(cfg or {}, LOCAL_CHECK_ID):
            return False
        heavy, label = classify(tool, data.get('tool_input'), cfg)
        if not heavy:
            return False
        folder = heavy_dir()
        MS._mkdir(folder)
        # DL54 F7: no pid and no host. The parent is the short-lived shell of this hook, gone before the next hook
        # runs, so a pid would drop a live call at once. heavy_end or slot_stale_min removes the record.
        rec = {'label': label, 'ts': time.time(), 'session': data.get('session_id')}
        path = os.path.join(folder, _heavy_key(data) + '.json')
        tmp = MS._write_tmp(folder, rec, '.new-')
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001 - tracking must never stop a tool call
        H.warn('local heavy tracking skipped (%s: %s)' % (type(exc).__name__, exc))
        return False


def heavy_end(data):
    """Drop this call from the heavy work in flight (PostToolUse and PostToolUseFailure). Never raises."""
    try:
        if data.get('tool_name') not in TRACKED_TOOLS:
            return False
        os.unlink(os.path.join(heavy_dir(), _heavy_key(data) + '.json'))
        return True
    except OSError:
        return False
    except Exception:  # noqa: BLE001
        return False


def local_heavy_limit(cfg=None):
    """local_heavy of the machine config; a project may lower it with `local_heavy`, never raise it."""
    limit = MS.machine_config()['local_heavy']
    mine = (cfg or {}).get('local_heavy')
    if isinstance(mine, int) and not isinstance(mine, bool) and 1 <= mine < limit:
        limit = mine
    return limit


def local_running(cfg=None, ledger=None):
    """[(kind, label)] of the heavy local work now: foreground calls and, from the ledger, local agents."""
    out = [('command', h['label']) for h in heavy_running(cfg)]
    if isinstance(ledger, dict):
        for a in H.running_agents(ledger, 'local'):
            out.append(('agent', str(a.get('task') or a.get('id') or 'agent')))
    return out


def local_refusal(running, limit, label):
    names = ', '.join('%s: %s' % r for r in running)
    return ('DL-91 local heavy work is at its limit (%d of %d running: %s), so new heavy work is held: not starting %s. '
            'What to do: wait for one to finish, or launch it in the cloud; nothing is killed or slowed. Limit: '
            'local_heavy in the machine config (%s) or .delivery/config.json (a project can only lower it).'
            % (len(running), limit, names or 'unknown', label, MS.config_path()))


def project_cfg(root):
    return H.load_config(root) if root else copy.deepcopy(H.DEFAULTS)


def state(cfg):
    """(sample, limits, over_list); raises when the machine cannot be measured."""
    lim = L.limits(cfg)
    s = L.sample()
    return s, lim, L.over(s, lim)


def describe(s, lim):
    return 'memory %s%% (limit %s%%), CPU %s%% (limit %s%%)' % (
        L._n(s['mem']), L._n(lim['memory_pct']), L._n(s['cpu']), L._n(lim['cpu_pct']))


def running_heavy_text():
    top = L.top_processes()
    parts = []
    if top['cpu']:
        parts.append('CPU: ' + ', '.join(top['cpu']))
    if top['mem']:
        parts.append('memory: ' + ', '.join(top['mem']))
    return '; '.join(parts) or 'process list unavailable'


def refusal(s, lim, exceeded, label):
    return ('DL-77 machine load is over its limit (%s; %s), so new heavy work is held: not starting %s. '
            'Running heavy now: %s. What to do: wait a few minutes and retry, or let/finish a running job; '
            'nothing is killed or slowed. Limits: load_limits in ~/.claude/luismc-delivery-machine.json '
            '(machine) or .delivery/config.json (project).'
            % (describe(s, lim), '; '.join(exceeded), label, running_heavy_text()))


def check_local(data, cfg, ledger=None):
    """DL-91 only: None when the local heavy limit leaves room for this call, else the refusal text. Fails open.
    The pre-tool hook runs it after the project rules, so their more specific refusal is shown first."""
    tool = data.get('tool_name')
    if tool not in GUARDED_TOOLS or not H.check_on(cfg, LOCAL_CHECK_ID):
        return None
    heavy, label = classify(tool, data.get('tool_input'), cfg)
    if not heavy:
        return None
    try:
        limit = local_heavy_limit(cfg)
        running = local_running(cfg, ledger)
        if len(running) >= limit:
            return local_refusal(running, limit, label)
    except Exception as exc:  # noqa: BLE001
        H.warn('local heavy limit skipped (%s: %s)' % (type(exc).__name__, exc))
    return None


def check_call(data, cfg, ledger=None, local=True):
    """None when the call may go on, else the refusal text. Fails open (warning on stderr) when unmeasurable.
    `ledger` (the project's, when it has one) lets the DL-91 count include running local agents. `local=False` leaves
    the DL-91 limit out (the pre-tool hook checks it after the project rules with check_local)."""
    tool = data.get('tool_name')
    if tool not in GUARDED_TOOLS:
        return None
    heavy, label = classify(tool, data.get('tool_input'), cfg)
    if not heavy:
        return None
    if local:
        held = check_local(data, cfg, ledger)
        if held:
            return held
    if not H.check_on(cfg, CHECK_ID):
        return None
    try:
        s, lim, exceeded = state(cfg)
    except Exception as exc:  # noqa: BLE001 - measurement failure must never trap a session
        H.warn('load guard skipped, cannot measure the machine (%s: %s)' % (type(exc).__name__, exc))
        return None
    return refusal(s, lim, exceeded, label) if exceeded else None


def notice(cfg):
    """A one-line non-blocking notice when the machine is over a limit, else None (DL-78). Fails open."""
    if not H.check_on(cfg, 'DL-78'):
        return None
    try:
        s, lim, exceeded = state(cfg)
    except Exception as exc:  # noqa: BLE001
        H.warn('load notice skipped, cannot measure the machine (%s: %s)' % (type(exc).__name__, exc))
        return None
    if not exceeded:
        return None
    return ('luismc-delivery DL-78: machine load is over its limit (%s; %s). Hold new heavy work (tests, builds, '
            'installs, local agents) until it drops; heavy tool calls are refused meanwhile. Nothing is killed.'
            % (describe(s, lim), '; '.join(exceeded)))


def with_notice(fn, event):
    """Run a hook main() and merge the load notice into its single JSON output (systemMessage; for SessionStart
    also additionalContext, which the model sees). Returns main()'s code."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = fn()
    text = buf.getvalue().strip()
    if H.hooks_off():
        if text:
            print(text)
        return code
    try:
        cfg = project_cfg(H.find_root(H.LAST_INPUT))
        msg = notice(cfg)
    except Exception as exc:  # noqa: BLE001
        H.warn('load notice skipped (%s: %s)' % (type(exc).__name__, exc))
        msg = None
    if not msg:
        if text:
            print(text)
        return code
    try:
        out = json.loads(text) if text else {}
        if not isinstance(out, dict):
            raise ValueError
    except ValueError:
        if text:
            print(text)
        out = {}
    out['systemMessage'] = (out['systemMessage'] + '\n' if out.get('systemMessage') else '') + msg
    if event == 'SessionStart':
        hso = out.setdefault('hookSpecificOutput', {'hookEventName': 'SessionStart'})
        hso['additionalContext'] = (hso.get('additionalContext', '') + '\n' + msg).strip()
    print(json.dumps(out))
    return code

