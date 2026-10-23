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
"""
import copy
import io
import json
import os
import re
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooklib as H  # noqa: E402
import load as L  # noqa: E402

CHECK_ID = 'DL-77'
SHELL_TOOLS = ('Bash', 'PowerShell')
GUARDED_TOOLS = SHELL_TOOLS + ('Agent', 'Workflow')

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


def check_call(data, cfg):
    """None when the call may go on, else the refusal text. Fails open (warning on stderr) when unmeasurable."""
    tool = data.get('tool_name')
    if tool not in GUARDED_TOOLS or not H.check_on(cfg, CHECK_ID):
        return None
    heavy, label = classify(tool, data.get('tool_input'), cfg)
    if not heavy:
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

