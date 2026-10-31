#!/usr/bin/env python3
"""Stop hook (DELIVERYSPEC section 5, D3, D8 Q-2, D9).

Blocks the end of a turn with {"decision": "block", "reason": ...} while the delivery ledger
or the last assistant text breaks a rule. Each finding names its DL id and the fix. The same
set of findings blocks at most enforcement.block_ceiling (default 3) times per session, then the turn ends
with a systemMessage (artifacts R8.4), so a session that cannot fix a finding never loops. With
enforcement.mode "warn" nothing blocks: the findings are shown as a systemMessage. Every block is appended to
.delivery/blocks.log when enforcement.log_every_block is true. Reads the
ledger read-only; never writes it. A project without .delivery/ is untouched.

The loop limit (config `stop_repeat_limit`, default 3, 0 = never): a finding that blocked `limit` turn ends in a row
with its key and the ledger fields it depends on unchanged stops blocking and is announced once per session.

Checks: DL-02 DL-03 DL-14 DL-18 DL-30 DL-31 DL-32 DL-33 DL-63 DL-64 DL-76 and Q-2.
Disable one in .delivery/config.json "checks_off", all with CLAUDE_DELIVERY_HOOKS=off.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooklib as H  # noqa: E402

MONTHS = {m: i + 1 for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}
CLOCK_RE = re.compile(r'\b(?:[01]?\d|2[0-3])[:h][0-5]\d\b')
DEPENDENCY_RE = re.compile(r'\b(?:after|once|when|since|from|depends?|dependent|based on|because|following|'
                           r'starts? at|started|waiting (?:for|on)|ci|build|run|merge|deploy|install|train)\b', re.I)
# `ETA` alone is a ledger field name or a noun ("adds the ETA for X"); it is a promise only when a time, an
# estimate or a vague "soon" follows it ("ETA 16:40", "ETA ~20 min", "the ETA is about 1 h", "ETA: soon")
ETA_RE = re.compile(r'\bETAs?\b(?=\s*[:=~]|\s+(?:(?:is|are)\s+)?(?:~|about|around|soon|shortly|later|tomorrow|in\b|by\b|at\b|\d))'
                    r'|\b(?:ready|done|finish(?:es|ed)?|due)\s+(?:soon|shortly)\b'
                    r'|\b(?:in|within|about|around|~)\s*~?\s*\d+(?:[.,]\d+)?\s*'
                    r'(?:-\s*\d+\s*)?(?:min(?:ute)?s?|h(?:ours?|rs?)?)\b|\bexpected (?:at|by|in)\b', re.I)
DURATION_RE = re.compile(r'\d+(?:[.,]\d+)?\s*(?:-\s*\d+\s*)?(?:min(?:ute)?s?|h(?:ours?|rs?)?)\b', re.I)
# a sentence that reports a measured duration, a saving or a cost is not an estimate (DL-31)
MEASURED_RE = re.compile(r'\b(?:took|taken|spent|saved?|saves|saving|savings|costs?|costing|cost|measured|lasted|elapsed|'
                         r'ran for|each|per|average|so far|already|was|were|had)\b', re.I)
TOMORROW_RE = re.compile(r"\btomorrow\b|\bnext round\b|\bin the morning\b|\bnext day\b|\bnext morning\b", re.I)
PAST_MIDNIGHT_RE = re.compile(r'\b(?:past|after) midnight\b|\b0[0-5][:h][0-5]\d\b', re.I)
FENCE_RE = re.compile(r'```.*?```', re.S)
CODE_SPAN_RE = re.compile(r'(`+)(?!`)(.+?)(?<!`)\1(?!`)', re.S)
TRAIN_WORD_RE = re.compile(r'^trains?\b', re.I)
LIST_ITEM_RE = re.compile(r'^\s*(?:\d+[.)]|[-*•])\s+(.*\S)\s*$')


# --- the last assistant text -------------------------------------------------------------

def last_assistant_text(data):
    msg = data.get('last_assistant_message')
    if isinstance(msg, str) and msg.strip():
        return msg
    path = data.get('transcript_path')
    if not isinstance(path, str):
        return ''
    text = ''
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                m = e.get('message') if isinstance(e, dict) else None
                if not isinstance(m, dict) or m.get('role') != 'assistant' and e.get('type') != 'assistant':
                    continue
                c = m.get('content')
                if isinstance(c, str):
                    parts = [c]
                elif isinstance(c, list):
                    parts = [b.get('text', '') for b in c if isinstance(b, dict) and b.get('type') == 'text']
                else:
                    parts = []
                joined = '\n'.join(p for p in parts if p).strip()
                if joined:
                    text = joined
    except OSError:
        return ''
    return text


def prose(text):
    """The reply without fenced code blocks."""
    return FENCE_RE.sub(' ', text)


def plain_prose(text):
    """The reply without fenced code blocks and inline code spans: words in code (a JSON key `trains`, a field
    `eta`) are names, not wording the owner reads."""
    return CODE_SPAN_RE.sub(' ', prose(text))


# --- text checks ---------------------------------------------------------------------------

def sentences(text):
    return [s for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]


def is_measured(sentence):
    """True for a sentence that states past or typical durations, not a forecast: a past/saving/cost verb, or a
    list of two or more durations (\"UI coding takes about 1 h, a full check 35-50 min, and CI about 20 min\")."""
    return bool(MEASURED_RE.search(sentence)) or len(DURATION_RE.findall(sentence)) >= 2


def check_eta_text(text):
    """DL-31 / D9. Findings (key, message) for the reply text."""
    out = []
    body = plain_prose(text)
    if TOMORROW_RE.search(body) and not (CLOCK_RE.search(body) and PAST_MIDNIGHT_RE.search(body)):
        m = TOMORROW_RE.search(body)
        out.append(('DL-31:tomorrow', 'DL-31 the reply defers with "%s". Give a computed clock time (past midnight if it '
                    'is) from the real start plus the typical duration, naming the dependency; no "tomorrow", '
                    '"next round" or "in the morning".' % m.group(0)))
    for line in body.splitlines():
        # a clock time or a dependency anywhere in the same bullet or line covers all its sentences
        line_clock, line_dep = bool(CLOCK_RE.search(line)), bool(DEPENDENCY_RE.search(line))
        for s in sentences(line):
            if not ETA_RE.search(s) or is_measured(s):
                continue
            missing = []
            if not (CLOCK_RE.search(s) or line_clock):
                missing.append('a clock time')
            if not (DEPENDENCY_RE.search(s) or line_dep):
                missing.append('the dependency it counts from')
            if missing:
                out.append(('DL-31:eta:' + s.strip()[:60], 'DL-31 an ETA lacks %s: "%s". Rewrite it as a clock time '
                            '(real start + typical duration, in the owner\'s zone) and name what it depends on, e.g. '
                            '"ready 16:40, 25 min after the CI run started 16:15".' % (' and '.join(missing), s.strip()[:120])))
    return out


def code_spans(body):
    return [m.span() for m in CODE_SPAN_RE.finditer(body)]


def check_label_text(text, cfg, ledger):
    """DL-64: train labels or branch names instead of RELEASE-n."""
    body = prose(text)
    hits = set()
    try:
        # the word train(s) counts in plain prose only; any other label (T-id, release/n) and branch names count
        # in inline code too, because DL-64 forbids showing them to the owner
        for m in re.finditer(cfg['train_label_re'], body):
            if TRAIN_WORD_RE.match(m.group(0)) and any(a <= m.start() < b for a, b in code_spans(body)):
                continue
            hits.add(m.group(0))
    except re.error:
        H.warn('train_label_re is not a valid regex')
    for t in ledger['trains']:
        for key in ('id', 'branch'):
            v = t.get(key)
            if isinstance(v, str) and v and v in body:
                hits.add(v)
    if not hits:
        return []
    return [('DL-64:' + '|'.join(sorted(hits)), 'DL-64 the reply says %s. Say RELEASE-n (the release number), never a '
             'train label or branch name.' % ', '.join('"%s"' % h for h in sorted(hits)))]


def trailing_questions(text):
    """The question lines of a numbered or bulleted list that closes the reply; [] when none (D8 Q-2)."""
    lines = [l for l in prose(text).rstrip().splitlines()]
    items = []
    for line in reversed(lines):
        if not line.strip():
            if items:
                break
            continue
        m = LIST_ITEM_RE.match(line)
        if not m:
            if items and line.startswith((' ', '\t')):
                continue          # wrapped continuation of an item
            break
        items.append(m.group(1))
    items.reverse()
    asked = [i for i in items if '?' in i]
    return asked if len(items) >= 2 and len(asked) * 2 >= len(items) else []


def check_questions_text(text):
    asked = trailing_questions(text)
    if not asked:
        return []
    return [('Q-2:' + asked[0][:40], 'Q-2 the reply ends with a list of %d questions for the owner. Ask them with '
             'AskUserQuestion calls (all open questions at once, context inside each question text), not as a list '
             'in the reply.' % len(asked))]


# --- ledger checks ---------------------------------------------------------------------------

def check_trains(ledger, cfg, at):
    out = []
    for t in H.trains_joined_unpushed(ledger, at, cfg['join_push_min']):
        out.append(('DL-02:' + str(t.get('id')), 'DL-02 %s is joined but not pushed and the previous train has been green '
                    'for more than %d min. Push it now (join.py --push), then open its ready PR.'
                    % (H.release_name(t), cfg['join_push_min'])))
    for t in H.trains_green_unmerged(ledger, at):
        out.append(('DL-03:' + str(t.get('id')), 'DL-03 %s is green and not merged. Merge it now (gh pr merge %s, after '
                    'ci_watch.py passed for its head), or record a hold with its reason: delivery_ledger.py hold.'
                    % (H.release_name(t), t.get('pr', 'N'))))
    for t in ledger['trains']:
        if not t.get('merged_at') or t.get('state') in H.TERMINAL_TRAIN:
            continue
        if H.on_hold(t, at):        # a recorded hold (delivery_ledger.py hold) suspends DL-14 and DL-18 until its `until`
            continue
        pr = t.get('pr', 'N')
        if not t.get('cleaned_at'):
            out.append(('DL-14:' + str(t.get('id')), 'DL-14 %s is merged and not cleaned. %s'
                        % (H.release_name(t), record_hint(cfg, 'cleanup_command', 'cleaned', pr,
                                                          'Run cleanup.py --pr %s' % pr))))
        if not (t.get('smoke') or {}).get('state'):
            out.append(('DL-18:' + str(t.get('id')), 'DL-18 %s is merged and production was not smoke-tested. %s'
                        % (H.release_name(t), record_hint(cfg, 'smoke_command', 'smoke', pr,
                                                          'Run the smoke step after its deploy'))))
    return out


def record_hint(cfg, cfg_key, subcommand, pr, fallback):
    """The sentence that names the command doing the work (the project's configured one, else `fallback`) and the
    plugin command that records its result in the ledger, which the hook reads (the project's scripts may not)."""
    configured = cfg.get(cfg_key)
    if isinstance(configured, str) and configured.strip():
        todo = 'Run `%s`' % configured.replace('{pr}', str(pr))
    else:
        todo = fallback
    ledger_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'delivery_ledger.py')
    return '%s, then record it with `python %s %s --pr %s` (it checks the facts and writes the ledger).' % (
        todo, ledger_py, subcommand, pr)


# --- loop limit (stop_repeat_limit) --------------------------------------------------------------

DEPENDS_TRAIN = ('state', 'pr', 'pushed_at', 'green_at', 'merged_at', 'live_at', 'cleaned_at', 'smoke', 'hold',
                 'release_no')
DEPENDS_AGENT = ('state', 'last_checked', 'eta', 'started')


def depends_on(ledger, key):
    """The ledger fields a finding depends on, as a JSON-able value: a train's or an agent's fields for a key that
    names one (DL-02/03/14/18/76, DL-30/32), nothing for the rest."""
    ident = key.split(':', 1)[1] if ':' in key else None
    if ident:
        for rows, fields in ((ledger['trains'], DEPENDS_TRAIN), (ledger['agents'], DEPENDS_AGENT)):
            for r in rows:
                if str(r.get('id')) == ident:
                    return {f: r.get(f) for f in fields}
    return None


def repeat_limit(found, ledger, root, sid, limit):
    """(still_blocking, newly_limited). A finding whose key and dependent ledger fields were the same on `limit`
    earlier turn ends stops blocking (the loop limit); one notice per session is returned for the findings that just
    hit the limit. A changed field or a new finding counts from 1 again. limit 0 = never."""
    if limit <= 0 or not found:
        return found, []
    state = H.read_state(root)
    skey = 'repeat:' + sid
    old = state.get(skey) if isinstance(state.get(skey), dict) else {}
    new, blocking, noticed = {}, [], []
    for key, msg in found:
        fp = H.fingerprint([key, json.dumps(depends_on(ledger, key), sort_keys=True, default=str)])
        prev = old.get(key) if isinstance(old.get(key), dict) else {}
        n = prev.get('n', 0) + 1 if prev.get('fp') == fp and isinstance(prev.get('n'), int) else 1
        entry = {'fp': fp, 'n': n, 'noticed': bool(prev.get('noticed')) if prev.get('fp') == fp else False}
        if n > limit:
            if not entry['noticed']:
                entry['noticed'] = True
                noticed.append((key, msg))
        else:
            blocking.append((key, msg))
        new[key] = entry
    state.pop(skey, None)
    state[skey] = new
    H.write_state(root, state)
    return blocking, noticed


def limit_notice(noticed, limit):
    rules = sorted({k.split(':')[0] for k, _ in noticed})
    names = sorted({(re.match(r'DL-\d+ (RELEASE-\d+|the train)\b', m) or [None, k])[1] for k, m in noticed})
    return ('luismc-delivery: letting the turn end after %d blocks with no change. %s for %s still open after %d tries; '
            'the turn is no longer blocked for it. Record it with the command named below, or ask the owner. %s'
            % (limit, '/'.join(rules), ', '.join(names), limit, ' '.join(m for _, m in noticed)))


def check_agents(ledger, cfg, at):
    out = []
    for a in ledger['agents']:
        if a.get('state') in H.TERMINAL_AGENT:
            continue
        name = a.get('task') or ','.join(a.get('tasks') or []) or a.get('id')
        eta = a.get('eta') if isinstance(a.get('eta'), dict) else {}
        if not (isinstance(eta.get('breakdown'), dict) and eta['breakdown']):
            out.append(('DL-30:' + str(a.get('id')), 'DL-30 agent %s was launched without an ETA breakdown. Record it '
                        'with: delivery_ledger.py agent-eta %s --setup N --work N --checks N --basis "<files touched>" '
                        '(minutes from the files touched, with the basis).' % (name, a.get('id') or name)))
        if a.get('state') != 'running':
            continue
        since = a.get('last_checked') or a.get('started')
        age = H.minutes_since(since, at)
        due = H.parse_ts(eta.get('due'))
        overdue = due is not None and due <= at and (H.parse_ts(a.get('last_checked')) or due) <= due
        if overdue or (age is not None and age > cfg['check_min']):
            out.append(('DL-32:' + str(a.get('id')), 'DL-32 agent %s %s. Check its log, branch and run status now '
                        '(a log older than the step\'s typical time means investigate), then the check is recorded.'
                        % (name, 'is past its due time without a check' if overdue
                           else 'was not checked for %d min' % age)))
    return out


# --- DL-76: one CI per release -----------------------------------------------------------------

def gh_json(argv, root):
    """`gh` JSON output, None on any failure (the check then stays silent)."""
    try:
        p = subprocess.run(['gh'] + argv, cwd=root, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=25)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def check_one_ci_per_release(root, ledger, cfg, gh=gh_json):
    """DL-76. From each merged, not yet cleaned train's merge commit, list the default-branch workflow runs and flag
    every job named in `pr_proven_jobs` that ran there on a tree the release PR already proved. `gh` is the seam."""
    names = [n.lower() for n in H.C.pr_proven_jobs(cfg)]
    if not names:
        return []
    out = []
    for t in ledger['trains']:
        if not t.get('merged_at') or not t.get('pr') or t.get('state') in H.TERMINAL_TRAIN:
            continue
        pr = gh(['pr', 'view', str(t['pr']), '--json', 'mergeCommit,baseRefName,headRefOid'], root)
        merge = ((pr or {}).get('mergeCommit') or {}).get('oid')
        if not merge or not pr.get('baseRefName'):
            continue
        trees = [((gh(['api', 'repos/{owner}/{repo}/git/commits/' + sha, '--jq', '{tree: .tree.sha}'], root) or {})
                  .get('tree')) for sha in (merge, pr.get('headRefOid') or '')]
        if not trees[0] or trees[0] != trees[1]:
            continue        # the base moved: the merge commit is a new tree and may be tested once
        runs = gh(['run', 'list', '--branch', pr['baseRefName'], '--commit', merge, '--limit', '50',
                   '--json', 'databaseId,workflowName'], root) or []
        repeated = []
        for r in runs:
            jobs = ((gh(['run', 'view', str(r.get('databaseId')), '--json', 'jobs'], root) or {}).get('jobs')) or []
            for j in jobs:
                n = str(j.get('name', ''))
                if j.get('conclusion') != 'skipped' and any(fnmatch.fnmatchcase(n.lower(), g) for g in names):
                    repeated.append('%s / %s' % (r.get('workflowName'), n))
        if repeated:
            out.append(('DL-76:' + str(t.get('id')), 'DL-76 %s merged and %s re-ran on %s on the same tree the PR proved: '
                        '%s. A release runs CI once: nothing after the merge re-runs what the release PR proved on the '
                        'same tree; only publish, deploy and production smoke run on the default branch. Remove those '
                        'jobs from the default-branch triggers (or gate them with a tree check).'
                        % (H.release_name(t), 'job' if len(repeated) == 1 else 'jobs', pr['baseRefName'],
                           ', '.join(sorted(set(repeated))[:6]))))
    return out


def in_flight(ledger):
    items = ['agent %s' % (a.get('task') or a.get('id')) for a in ledger['agents'] if a.get('state') == 'running']
    items += ['%s CI' % H.release_name(t) for t in ledger['trains'] if t.get('state') in ('pushed', 'ci')]
    items += ['install %s' % i.get('product') for i in ledger['installs'] if i.get('state') == 'installing']
    items += ['job %s' % j.get('id') for j in ledger['jobs'] if j.get('state') in ('running', 'waiting-ci')]
    return items


def check_watcher(ledger, cfg, at):
    items = in_flight(ledger)
    if not items:
        return []
    for w in ledger['watchers']:
        age = H.minutes_since(w.get('heartbeat_at'), at)
        if age is not None and age < cfg['watcher_min']:
            return []
    return [('DL-33', 'DL-33 work is in flight (%s) and no watcher has a heartbeat in the last %d min. Start '
             'delivery_watch.py in the background (run_in_background) before ending the turn.'
             % (', '.join(items[:4]), cfg['watcher_min']))]


def parse_expected(text, at):
    """A registry 'expected' as an aware datetime (end of day for a bare date); None when not a date."""
    if not isinstance(text, str):
        return None
    t = H.parse_ts(text.strip())
    if t is not None:
        return t if 'T' in text else t + timedelta(days=1)
    m = re.search(r'\b(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?(?:\s+(\d{4}))?(?:[ ,]+(\d{1,2}):(\d{2}))?', text)
    if not m or m.group(2).lower() not in MONTHS:
        return None
    year = int(m.group(3)) if m.group(3) else at.year
    try:
        d = datetime(year, MONTHS[m.group(2).lower()], int(m.group(1)), tzinfo=at.tzinfo)
    except ValueError:
        return None
    if not m.group(3) and d - at > timedelta(days=180):
        d = d.replace(year=year - 1)
    if m.group(4):
        return d.replace(hour=int(m.group(4)), minute=int(m.group(5)))
    return d + timedelta(days=1)


def check_registry(root, cfg, at):
    reg = H.read_json(os.path.join(root, 'docs', 'artifacts', 'registry.json'))
    tasks = reg.get('tasks') if isinstance(reg, dict) else None
    if not isinstance(tasks, list):
        return []
    out = []
    for t in tasks:
        if not isinstance(t, dict) or t.get('status') not in cfg['registry_open']:
            continue
        exp = parse_expected(t.get('expected'), at)
        if exp is not None and exp <= at:
            out.append(('DL-63:' + str(t.get('id')), 'DL-63 row %s (%s) is %s with Expected "%s" in the past. Close it if '
                        'it shipped, or set a new real Expected time (task-status-update / task-add), then publish Full Progress.'
                        % (t.get('id'), t.get('item', ''), t.get('status'), t.get('expected'))))
    return out


# --- main ------------------------------------------------------------------------------------

def findings(root, data, cfg):
    at = H.now()
    ledger = H.load_ledger(root)
    text = last_assistant_text(data)
    out = []
    out += check_trains(ledger, cfg, at)
    out += check_agents(ledger, cfg, at)
    out += check_watcher(ledger, cfg, at)
    out += check_registry(root, cfg, at)
    out += check_one_ci_per_release(root, ledger, cfg)
    if text:
        out += check_eta_text(text)
        out += check_label_text(text, cfg, ledger)
        out += check_questions_text(text)
    return [(k, m) for k, m in out if H.check_on(cfg, k.split(':')[0])]


def main():
    if H.hooks_off():
        return 0
    data = H.read_input()
    root = H.find_root(data)
    if not root:
        return 0
    cfg = H.load_config(root)
    found = findings(root, data, cfg)
    enf = H.C.enforcement(cfg)
    if enf['mode'] == 'warn':
        if found:
            print(json.dumps({'systemMessage': 'luismc-delivery (warn mode, nothing blocked): '
                              + '; '.join(m for _, m in found)}))
        return 0
    sid = str(data.get('session_id') or 'default')
    limit = H.repeat_limit(cfg, enf['block_ceiling'])
    found, noticed = repeat_limit(found, H.load_ledger(root), root, sid, limit)
    notice = {'systemMessage': limit_notice(noticed, limit)} if noticed else {}
    verdict, blocks = H.block_decision(root, sid, [k for k, _ in found], enf['block_ceiling'])
    if verdict == 'clear':
        if notice:
            print(json.dumps(notice))
        return 0
    if verdict == 'release':
        print(json.dumps({'systemMessage': 'luismc-delivery: letting the turn end after %d blocks with no change. '
                          'Still open: %s' % (enf['block_ceiling'], '; '.join(m for _, m in found))}))
        return 0
    for _, m in found:
        H.log_block(root, cfg, 'stop', m)
    reason = 'Delivery checks failed. Fix these in this turn:\n' + '\n'.join('- ' + m for _, m in found)
    print(json.dumps(dict(notice, decision='block', reason=reason)))
    return 0


if __name__ == '__main__':
    try:
        import load_guard as G
        code = G.with_notice(main, 'Stop')     # DL-78: one non-blocking load notice per turn
    except Exception as exc:   # fail open: a broken hook must not trap the session
        H.warn('stop hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
