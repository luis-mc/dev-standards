#!/usr/bin/env python3
"""SessionStart hook (DELIVERYSPEC section 5, D1).

Prints hookSpecificOutput.additionalContext with a short ledger summary (trains, agents
overdue, installs, Full Progress age), trains that gh reports merged but the ledger still
shows open (the catch-up; this hook only reports, delivery_ledger.py writes), the rule to
keep an hourly check-in, and the prompt to start delivery_watch.py when no watcher has a
fresh heartbeat. Also delivers the plugin's rules/ files (clarifying-questions, Q-1..Q-5) every session. Read-only; a project
without .delivery/ gets nothing.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooklib as H  # noqa: E402


RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rules')
RULE_FILES = ('clarifying-questions.md',)
RULE_TAG_RE = re.compile(r'[ \t]*<!-- (?:check:[^>]*|advice) -->')


def rules_text():
    """The plugin's rule files (tags stripped: they are for maintainers and tools/test_rule_tags.py)."""
    out = []
    for name in RULE_FILES:
        try:
            with open(os.path.join(RULES_DIR, name), encoding='utf-8') as f:
                out.append(RULE_TAG_RE.sub('', f.read()).strip())
        except OSError:
            H.warn('rules/%s cannot be read; the rule was not delivered' % name)
    return '\n\n'.join(out)


def merged_catchup(root, ledger):
    open_prs = {t['pr']: t for t in ledger['trains']
                if t.get('pr') is not None and not t.get('merged_at') and t.get('state') not in H.TERMINAL_TRAIN}
    if not open_prs:
        return []
    r = H.gh(root, ['pr', 'list', '--state', 'merged', '--limit', '30', '--json', 'number,mergedAt'])
    if not r or r[0] != 0:
        return []
    try:
        merged = json.loads(r[1])
    except ValueError:
        return []
    out = []
    for pr in merged if isinstance(merged, list) else []:
        t = open_prs.get(pr.get('number')) if isinstance(pr, dict) else None
        if t:
            out.append('%s (PR #%s) merged at %s but the ledger still shows %s: record it '
                       '(delivery_ledger.py train merged) and run cleanup.py --pr %s, then smoke-test.'
                       % (H.release_name(t), pr['number'], pr.get('mergedAt'), t.get('state'), pr['number']))
    return out


def summary(root, cfg, ledger, at):
    lines = []
    by_state = {}
    for t in ledger['trains']:
        if t.get('state') not in H.TERMINAL_TRAIN:
            by_state.setdefault(t.get('state') or '?', []).append(H.release_name(t))
    lines.append('Trains: ' + ('; '.join('%s: %s' % (s, ', '.join(n)) for s, n in sorted(by_state.items())) or 'none open'))
    running = H.running_agents(ledger)
    overdue = []
    for a in running:
        due = H.parse_ts((a.get('eta') or {}).get('due'))
        age = H.minutes_since(a.get('last_checked') or a.get('started'), at)
        if (due is not None and due <= at) or (age is not None and age > cfg['check_min']):
            overdue.append(str(a.get('task') or a.get('id')))
    lines.append('Agents: %d running (%d cloud, %d local); needing a check: %s'
                 % (len(running), len(H.running_agents(ledger, 'cloud')), len(H.running_agents(ledger, 'local')),
                    ', '.join(overdue) or 'none'))
    installing = [i.get('product') for i in ledger['installs'] if i.get('state') == 'installing']
    lines.append('Installs: ' + (', '.join('%s installing' % p for p in installing) or 'none running'))
    fp = [p for p in ledger['publishes'] if p.get('artifact') == 'full-progress']
    age = H.minutes_since(fp[0].get('last_at'), at) if fp else None
    lines.append('Full Progress: ' + ('never published' if age is None else 'published %d min ago' % age))
    return lines


def _cmdline_ok(pid):
    """False only when the process's command line is readable and is not a delivery_watch (pid reuse)."""
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as f:
            return b'delivery_watch' in f.read()
    except OSError:
        return True


def stop_pid(pid):
    """Stop one process by its recorded pid. Never by name."""
    import signal
    if not isinstance(pid, int) or pid <= 1 or pid == os.getpid() or not _cmdline_ok(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        return False
    return True


def spawn_watcher(root):
    """Start the installed plugin's watcher, detached."""
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'delivery_watch.py')
    kw = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
    if os.name == 'nt':
        kw['creationflags'] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw['start_new_session'] = True
    try:
        subprocess.Popen([sys.executable, script, '--root', str(root)], **kw)
        return True
    except OSError:
        return False


def rearm_old_watchers(root, ledger, installed):
    """DL98: a watcher started from an older plugin version is stopped (by its recorded pid) and the newest is
    started. A watcher with no version stamp is older. Same version: left alone. Returns (messages, stopped pids)."""
    import delivery_ledger as L
    msgs, stopped = [], []
    want = L.version_key(installed)
    if not want:
        return msgs, stopped
    for w in ledger['watchers']:
        if w.get('kind') != 'delivery_watch':
            continue
        have = L.version_key(w.get('version'))
        if have >= want:
            continue
        if stop_pid(w.get('pid')):
            stopped.append(w.get('pid'))
            msgs.append('stopped delivery_watch pid %s (plugin %s, installed %s)'
                        % (w.get('pid'), w.get('version') or 'unstamped', installed))
    if stopped:
        msgs.append('started the installed delivery_watch' if spawn_watcher(root)
                    else 'could not start delivery_watch: start it in the background')
    return msgs, stopped


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
    parts = ['luismc-delivery: delivery ledger summary (' + at.strftime('%Y-%m-%d %H:%M UTC') + ')']
    parts += ['- ' + l for l in summary(root, cfg, ledger, at)]
    catch = merged_catchup(root, ledger)
    if catch:
        parts.append('Catch-up (merged on GitHub, open in the ledger):')
        parts += ['- ' + c for c in catch]
    parts.append('Keep an hourly check-in: create an hourly cron at the start of the session that checks the '
                 'ledger, the running agents and Full Progress (published at least hourly while work is open).')
    try:
        H.C.load_tz(cfg.get('tz') or 'UTC')
    except ValueError as exc:
        parts.append('WARNING: ' + str(exc) + ' Run delivery_doctor.py.')
    try:
        import delivery_ledger as _L
        rearm, gone = rearm_old_watchers(root, ledger, _L.plugin_version())
    except Exception as exc:     # fail open
        H.warn('watcher re-arm skipped (%s: %s)' % (type(exc).__name__, exc))
        rearm, gone = [], []
    if rearm:
        parts.append('Watcher re-armed (DL98): ' + '; '.join(rearm) + '.')
    fresh = any((H.minutes_since(w.get('heartbeat_at'), at) or 1e9) < cfg['watcher_min'] for w in ledger['watchers']
                if w.get('pid') not in gone) or bool(gone and rearm and rearm[-1].startswith('started'))
    if not fresh:
        parts.append('No watcher heartbeat in the last %d min: start delivery_watch.py in the background '
                     '(run_in_background) before launching work.' % cfg['watcher_min'])
    rules = rules_text()
    if rules:
        parts.append('luismc-delivery: rules for work in this project (DELIVERYSPEC D8)\n\n' + rules)
    out = {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': '\n'.join(parts)}}
    print(json.dumps(out))
    return 0


if __name__ == '__main__':
    try:
        import load_guard as G
        code = G.with_notice(main, 'SessionStart')     # DL-78: tell the session to hold new heavy work
    except Exception as exc:   # fail open
        H.warn('session-start hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
