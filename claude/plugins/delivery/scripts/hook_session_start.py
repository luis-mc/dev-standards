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
    fresh = any((H.minutes_since(w.get('heartbeat_at'), at) or 1e9) < cfg['watcher_min'] for w in ledger['watchers'])
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
        code = main()
    except Exception as exc:   # fail open
        H.warn('session-start hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
