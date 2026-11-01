#!/usr/bin/env python3
"""Tests for the luismc-delivery hooks (Stop, PreToolUse, SessionStart; DELIVERYSPEC section 5).

Feeds hook input to each script in a throwaway project with a .delivery/ folder and a
fixture ledger (schema 1, DELIVERYSPEC section 2). No network: gh is a stub through
DELIVERY_GH, the clock is DELIVERY_NOW.

Run: python -I tools/test_delivery_hooks.py
Standard library only. Prints "N passed, 0 failed" and exits 0 when all pass.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'delivery')
SCRIPTS = os.path.join(PLUGIN, 'scripts')
NOW = '2026-10-14T20:00:00+00:00'


def iso(minutes_ago):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(NOW) - timedelta(minutes=minutes_ago)).isoformat()


class Project:
    def __init__(self, ledger=None, config=None, optin=True, registry=None):
        self.dir = tempfile.mkdtemp(prefix='dlv-')
        if optin:
            os.makedirs(os.path.join(self.dir, '.delivery'))
            if ledger is not None:
                self.write('.delivery/ledger.json', ledger)
            if config is not None:
                self.write('.delivery/config.json', config)
        if registry is not None:
            os.makedirs(os.path.join(self.dir, 'docs', 'artifacts'))
            self.write('docs/artifacts/registry.json', {'tasks': registry})
        self.gh_out = None
        self.repo = 'luis-mc/here'

    def write(self, rel, value):
        with open(os.path.join(self.dir, rel), 'w', encoding='utf-8') as f:
            f.write(value if isinstance(value, str) else json.dumps(value))

    def stub_gh(self, view=None, merged=None, runs=None):
        """runs: {head sha: [{'status', 'conclusion'}]} for `gh run list --commit`; every call lands in gh_calls.log."""
        body = ("import sys, json\na = sys.argv[1:]\n"
                "open(%r, 'a').write(' '.join(a) + '\\n')\n"
                "if a[:2] == ['run', 'list']:\n    print(json.dumps(%r.get(a[a.index('--commit') + 1], [])))\n"
                "elif a[:2] == ['pr', 'view']:\n    print(json.dumps(%r))\n"
                "elif a[:2] == ['repo', 'view']:\n    print(json.dumps({'nameWithOwner': %r}))\n"
                "elif a[:2] == ['pr', 'list']:\n    print(json.dumps(%r))\n"
                % (os.path.join(self.dir, 'gh_calls.log'), runs or {}, view or {}, self.repo, merged or []))
        self.write('gh_stub.py', body)
        return os.path.join(self.dir, 'gh_stub.py')

    def run(self, script, data, env=None):
        e = dict(os.environ, DELIVERY_NOW=NOW)
        e.pop('CLAUDE_DELIVERY_HOOKS', None)
        e.update(env or {})
        data = dict({'cwd': self.dir, 'session_id': 's1'}, **data)
        p = subprocess.run([sys.executable, '-I', os.path.join(SCRIPTS, script)], input=json.dumps(data).encode(),
                           capture_output=True, env=e, timeout=60)
        out = p.stdout.decode().strip()
        return p.returncode, (json.loads(out) if out else None), p.stderr.decode()

    def stop(self, text='', **extra):
        return self.run('hook_stop.py', dict({'last_assistant_message': text}, **extra))

    def pre(self, tool, tool_input, env=None):
        return self.run('hook_pre_tool.py', {'tool_name': tool, 'tool_input': tool_input}, env)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def train(**kw):
    t = {'id': 'T-1', 'release_no': 29, 'branch': 'release/29', 'pr': 412, 'state': 'ci', 'hold': None,
         'cargo': [], 'ci': {}, 'smoke': {}}
    t.update(kw)
    return t


def agent(**kw):
    a = {'task': 'DV1', 'where': 'cloud', 'id': 'a1', 'owns': [], 'started': iso(10), 'last_checked': iso(5),
         'eta': {'total_min': 25, 'breakdown': {'setup': 5, 'work': 12, 'checks': 8}, 'due': iso(-15)},
         'state': 'running'}
    a.update(kw)
    return a


def ledger(**kw):
    base = {'schema': 1, 'trains': [], 'agents': [], 'jobs': [], 'installs': [], 'publishes': [], 'runners': [],
            'watchers': [{'pid': 1, 'kind': 'delivery_watch', 'heartbeat_at': iso(2)}], 'owner_questions': [],
            'events': []}
    base.update(kw)
    return base


TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def blocked(res):
    return res[1] is not None and res[1].get('decision') == 'block'


def reason(res):
    return (res[1] or {}).get('reason', '')


def denied(res):
    h = (res[1] or {}).get('hookSpecificOutput') or {}
    return h.get('permissionDecision') == 'deny'


def why(res):
    return ((res[1] or {}).get('hookSpecificOutput') or {}).get('permissionDecisionReason', '')


def expect_block(proj, tag, text='', **kw):
    r = proj.stop(text, **kw)
    assert blocked(r), (tag, r)
    assert tag in reason(r), (tag, reason(r))
    return r


def expect_pass(r):
    assert r[0] == 0 and r[1] is None, r


# --- opt-in and switches -------------------------------------------------------------------

@test
def optin_no_delivery_folder_is_silent():
    p = Project(optin=False)
    expect_pass(p.stop('ETA in 20 minutes. tomorrow'))
    expect_pass(p.pre('Bash', {'command': 'gh pr merge --auto 5'}))
    expect_pass(p.run('hook_session_start.py', {}))
    p.close()


@test
def env_switch_turns_everything_off():
    p = Project(ledger(trains=[train(green_at=iso(30))]))
    r = p.run('hook_stop.py', {'last_assistant_message': ''}, {'CLAUDE_DELIVERY_HOOKS': 'off'})
    expect_pass(r)
    p.close()


@test
def clean_ledger_passes():
    p = Project(ledger())
    expect_pass(p.stop('All done.'))
    p.close()


@test
def checks_off_config():
    p = Project(ledger(trains=[train(green_at=iso(30), state='green')]), {'checks_off': ['DL-03']})
    expect_pass(p.stop(''))
    p.close()


# --- Stop: ledger checks ---------------------------------------------------------------------

@test
def dl02_joined_unpushed_after_previous_green():
    prev = train(id='T-1', release_no=28, state='ci', green_at=iso(9), merged_at=iso(8), cleaned_at=iso(7),
                 smoke={'state': 'ok'})
    nxt = train(id='T-2', release_no=29, state='joined', joined_at=iso(20))
    p = Project(ledger(trains=[prev, nxt]))
    expect_block(p, 'DL-02')
    p.close()


@test
def dl02_not_yet_five_minutes_passes():
    prev = train(id='T-1', release_no=28, state='merged', green_at=iso(3), merged_at=iso(2), cleaned_at=iso(1),
                 smoke={'state': 'ok'})
    nxt = train(id='T-2', release_no=29, state='joined')
    p = Project(ledger(trains=[prev, nxt]))
    expect_pass(p.stop(''))
    p.close()


@test
def dl03_green_unmerged_blocks_and_hold_allows():
    t = train(state='green', green_at=iso(30))
    p = Project(ledger(trains=[t]))
    expect_block(p, 'DL-03')
    p.close()
    t['hold'] = {'reason': 'owner asked', 'by': 'owner'}
    p = Project(ledger(trains=[t]))
    expect_pass(p.stop(''))
    p.close()


@test
def dl14_and_dl18_merged_train():
    t = train(state='merged', green_at=iso(30), merged_at=iso(20))
    p = Project(ledger(trains=[t]))
    r = p.stop('')
    assert 'DL-14' in reason(r) and 'DL-18' in reason(r), r
    p.close()
    t.update(cleaned_at=iso(5), smoke={'state': 'ok'})
    p = Project(ledger(trains=[t]))
    expect_pass(p.stop(''))
    p.close()


@test
def dl14_dl18_hold_suppresses_until_it_lapses():
    held = {'reason': 'catalogue check', 'by': 'rule', 'until': iso(-40)}
    t = train(state='merged', green_at=iso(30), merged_at=iso(20), hold=held)
    p = Project(ledger(trains=[t]))
    expect_pass(p.stop(''))
    p.close()
    t['hold'] = dict(held, until=iso(1))
    p = Project(ledger(trains=[t]))
    r = p.stop('')
    assert 'DL-14' in reason(r) and 'DL-18' in reason(r), r
    p.close()


@test
def dl06_cross_repo_pr_is_not_judged_by_the_current_repos_ledger_train():
    p = Project(ledger(trains=[train(pr=426, ci={'head_sha': 'old', 'state': 'running'})]))
    gh = p.stub_gh(view={'number': 426, 'headRefOid': 'other'}, runs={'other': OK_RUNS})
    expect_pass(bash(p, 'gh pr merge 426 --repo luis-mc/other --squash', {'DELIVERY_GH': gh}))
    r = bash(p, 'gh pr merge 426 --squash', {'DELIVERY_GH': gh})
    assert denied(r) and 'DL-06' in why(r), r
    p.close()
    # a train that carries the repo is still gated, against that repo's PR head
    p = Project(ledger(trains=[train(pr=426, repo='luis-mc/other', ci={'head_sha': 'good', 'state': 'success'})]))
    gh = p.stub_gh(view={'number': 426, 'headRefOid': 'good'})
    expect_pass(bash(p, 'gh pr merge 426 --repo luis-mc/other', {'DELIVERY_GH': gh}))
    gh = p.stub_gh(view={'number': 426, 'headRefOid': 'newer'})
    assert denied(bash(p, 'gh pr merge 426 --repo luis-mc/other', {'DELIVERY_GH': gh}))
    p.close()


@test
def dl30_agent_without_eta_breakdown():
    p = Project(ledger(agents=[agent(eta={})]))
    expect_block(p, 'DL-30')
    p.close()


@test
def dl32_watcher_recorded_check_counts_and_stalled_blocks():
    # DS33: the watcher records last_checked itself; a fresh check passes, a stalled flag still blocks
    p = Project(ledger(agents=[agent(last_checked=iso(2), started=iso(300), check_note='PR #7 draft')]))
    expect_pass(p.stop(''))
    p.close()
    p = Project(ledger(agents=[agent(last_checked=iso(2), stalled=True, check_note='STALLED: no activity for 70 min')]))
    expect_block(p, 'DL-32')
    p.close()


@test
def dl32_unchecked_30_min_and_past_due():
    p = Project(ledger(agents=[agent(last_checked=iso(45))]))
    expect_block(p, 'DL-32')
    p.close()
    due = agent(last_checked=iso(25), started=iso(60))
    due['eta']['due'] = iso(10)
    p = Project(ledger(agents=[due]))
    expect_block(p, 'DL-32')
    p.close()
    ok = agent(last_checked=iso(1), started=iso(60))
    ok['eta']['due'] = iso(10)
    p = Project(ledger(agents=[ok]))
    expect_pass(p.stop(''))
    p.close()


@test
def dl33_in_flight_without_fresh_watcher():
    p = Project(ledger(agents=[agent()], watchers=[{'pid': 1, 'heartbeat_at': iso(25)}]))
    expect_block(p, 'DL-33')
    p.close()
    p = Project(ledger(agents=[agent()], watchers=[]))
    expect_block(p, 'DL-33')
    p.close()
    p = Project(ledger(watchers=[]))                      # nothing in flight: no watcher needed
    expect_pass(p.stop(''))
    p.close()


@test
def dl63_open_registry_row_with_past_expected():
    rows = [{'id': 'X1', 'item': 'Thing', 'status': 'Running', 'expected': '10 Oct'},
            {'id': 'X2', 'item': 'Done thing', 'status': 'Live', 'expected': '10 Oct'},
            {'id': 'X3', 'item': 'Later', 'status': 'Waiting', 'expected': '20 Oct'}]
    p = Project(ledger(), registry=rows)
    r = expect_block(p, 'DL-63')
    assert 'X1' in reason(r) and 'X2' not in reason(r) and 'X3' not in reason(r), r
    p.close()


# --- Stop: text checks -----------------------------------------------------------------------

@test
def dl31_tomorrow_and_next_round():
    p = Project(ledger())
    expect_block(p, 'DL-31', 'The rest lands tomorrow.')
    p.close()
    p = Project(ledger())
    expect_block(p, 'DL-31', 'Picking this up next round.')
    p.close()
    p = Project(ledger())
    expect_pass(p.stop('Smoke test ready at 01:40 (past midnight), 25 min after the CI run starts.'))
    p.close()


@test
def dl31_eta_needs_clock_time_and_dependency():
    p = Project(ledger())
    expect_block(p, 'DL-31', 'The agent should be done in about 20 minutes.')
    p.close()
    p = Project(ledger())
    expect_block(p, 'DL-31', 'ETA 16:40.')
    p.close()
    p = Project(ledger())
    expect_pass(p.stop('Ready at 16:40, 25 min after the CI run started at 16:15.'))
    p.close()


@test
def dv396_stop_hook_false_alarms():
    p = Project(ledger())
    expect_pass(p.stop('| `trains` | the releases, with their PR and state |'))
    expect_pass(p.stop('- **I** add the rows the hooks miss, like the ETA for DV395.'))
    expect_block(p, 'DL-64', 'The trains are green.')
    expect_block(p, 'DL-31', 'ETA ~20 min')
    expect_block(p, 'DL-64', 'Pushed `release/29` for review.')
    p.close()


@test
def dl64_train_labels_instead_of_release_n():
    p = Project(ledger(trains=[train(state='cleaned', merged_at=iso(9), cleaned_at=iso(8), smoke={'state': 'ok'})]))
    expect_block(p, 'DL-64', 'Pushed release/29 for review.')
    p.close()
    p = Project(ledger())
    expect_block(p, 'DL-64', 'Train T-2026-10-14-01 is green.')
    p.close()
    p = Project(ledger())
    expect_pass(p.stop('RELEASE-29 is green.'))
    p.close()
    p = Project(ledger(), {'train_label_re': r'\bbatch-\d+\b'})
    expect_block(p, 'DL-64', 'batch-3 is out.')
    p.close()


@test
def q2_closing_list_of_questions_blocks():
    text = 'Done with the work.\n\nQuestions for you:\n1. Should I merge now?\n2. Which cap do you want?\n'
    p = Project(ledger())
    expect_block(p, 'Q-2', text)
    p.close()
    p = Project(ledger())
    expect_pass(p.stop('Done.\n\n- built the hook\n- wrote the tests\n'))
    p.close()
    p = Project(ledger())
    expect_pass(p.stop('Questions are in the wizard.\n\n1. one?\n2. two?\n\nThat is all, thanks for waiting.'))
    p.close()


@test
def transcript_path_is_read():
    p = Project(ledger())
    lines = [{'type': 'user', 'message': {'role': 'user', 'content': 'hi'}},
             {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
                 {'type': 'text', 'text': 'Back tomorrow.'}]}}]
    p.write('t.jsonl', '\n'.join(json.dumps(l) for l in lines))
    r = p.run('hook_stop.py', {'transcript_path': os.path.join(p.dir, 't.jsonl')})
    assert blocked(r) and 'DL-31' in reason(r), r
    p.close()


# --- Stop: fingerprint and ceiling -------------------------------------------------------------

@test
def ceiling_three_blocks_then_release_and_new_fingerprint_restarts():
    p = Project(ledger(trains=[train(state='green', green_at=iso(30))]))
    for _ in range(3):
        assert blocked(p.stop('')), 'should block'
    r = p.stop('')
    assert r[1] and 'decision' not in r[1] and 'letting the turn end' in r[1]['systemMessage'], r
    # the problem changes: a new fingerprint blocks again
    lg = ledger(trains=[train(state='green', green_at=iso(30)), train(id='T-9', release_no=30, state='green',
                                                                      green_at=iso(30))])
    p.write('.delivery/ledger.json', lg)
    assert blocked(p.stop(''))
    # fixed: state clears
    p.write('.delivery/ledger.json', ledger())
    expect_pass(p.stop(''))
    assert 's1' not in json.load(open(os.path.join(p.dir, '.delivery', 'hook-state.json')))
    p.close()


# --- enforcement config (0.2.0) -------------------------------------------------------------------

def read_log(p):
    path = os.path.join(p.dir, '.delivery', 'blocks.log')
    return open(path, encoding='utf-8').read().splitlines() if os.path.exists(path) else []


@test
def block_ceiling_comes_from_config():
    p = Project(ledger(trains=[train(state='green', green_at=iso(30))]), config={'enforcement': {'block_ceiling': 1}})
    assert blocked(p.stop(''))
    r = p.stop('')
    assert r[1] and 'decision' not in r[1] and 'after 1 blocks' in r[1]['systemMessage'], r
    q = Project(ledger(trains=[train(state='green', green_at=iso(30))]), config={'enforcement': {'block_ceiling': 5}})
    for _ in range(5):
        assert blocked(q.stop(''))
    assert not blocked(q.stop(''))
    p.close()
    q.close()


@test
def warn_mode_never_blocks_and_logs_nothing():
    cfg = {'enforcement': {'mode': 'warn', 'log_every_block': True}}
    p = Project(ledger(trains=[train(state='green', green_at=iso(30))]), config=cfg)
    r = p.stop('')
    assert r[1] and 'decision' not in r[1] and 'warn mode' in r[1]['systemMessage'] and 'DL-03' in r[1]['systemMessage'], r
    r = p.pre('Bash', {'command': 'gh pr merge 5 --auto'})
    assert r[1] and 'hookSpecificOutput' not in r[1] and 'DL-05' in r[1]['systemMessage'], r
    assert read_log(p) == []
    p.close()


@test
def log_every_block_appends_time_hook_rule_message():
    p = Project(ledger(trains=[train(state='green', green_at=iso(30))]), config={'enforcement': {'log_every_block': True}})
    assert blocked(p.stop(''))
    assert blocked(p.stop(''))
    p.pre('Bash', {'command': 'gh pr merge 5 --auto'})
    lines = read_log(p)
    assert len(lines) == 3, lines
    t, hook, rule, msg = lines[0].split('\t')
    assert t == '2026-10-14T20:00:00Z' and hook == 'stop' and rule == 'DL-03' and 'is green and not merged' in msg, lines
    assert lines[2].split('\t')[1:3] == ['pre-tool', 'DL-05'], lines
    p.close()


@test
def no_blocks_log_by_default_or_when_nothing_blocks():
    p = Project(ledger(trains=[train(state='green', green_at=iso(30))]))
    assert blocked(p.stop(''))
    assert read_log(p) == []
    q = Project(ledger(), config={'enforcement': {'log_every_block': True}})
    expect_pass(q.stop(''))
    assert read_log(q) == []
    p.close()
    q.close()


# --- PreToolUse: Bash ---------------------------------------------------------------------------

def bash(p, cmd, env=None):
    return p.pre('Bash', {'command': cmd}, env)


@test
def dl05_auto_merge_denied():
    p = Project(ledger())
    r = bash(p, 'gh pr merge 5 --auto --squash')
    assert denied(r) and 'DL-05' in why(r), r
    p.close()


@test
def dl06_merge_needs_ledger_ci_success_for_head():
    t = train(pr=412, ci={'head_sha': 'abc', 'state': 'success'})
    p = Project(ledger(trains=[t]))
    gh = p.stub_gh(view={'number': 412, 'headRefOid': 'abc'})
    expect_pass(bash(p, 'gh pr merge 412 --squash', {'DELIVERY_GH': gh}))
    gh = p.stub_gh(view={'number': 412, 'headRefOid': 'newer'})
    r = bash(p, 'gh pr merge 412 --squash', {'DELIVERY_GH': gh})
    assert denied(r) and 'DL-06' in why(r), r
    p.close()
    p = Project(ledger(trains=[train(pr=412, ci={'head_sha': 'abc', 'state': 'running'})]))
    gh = p.stub_gh(view={'number': 412, 'headRefOid': 'abc'})
    assert denied(bash(p, 'gh pr merge 412', {'DELIVERY_GH': gh}))
    p.close()
    p = Project(ledger())
    gh = p.stub_gh(view={'number': 7, 'headRefOid': 'abc'})
    assert denied(bash(p, 'gh pr merge 7', {'DELIVERY_GH': gh}))
    p.close()


def gh_calls(p):
    try:
        with open(os.path.join(p.dir, 'gh_calls.log'), encoding='utf-8') as f:
            return f.read().splitlines()
    except OSError:
        return []


OK_RUNS = [{'status': 'completed', 'conclusion': 'success'}] * 2
MERGE_FORMS = ['gh pr merge 85 -R luis-mc/dev-standards --squash', 'gh pr merge 85 --repo luis-mc/dev-standards',
               'gh pr merge 85 --repo=luis-mc/dev-standards', 'gh pr merge -R luis-mc/dev-standards 85',
               'gh pr merge https://github.com/luis-mc/dev-standards/pull/85 --squash']


@test
def dl06_foreign_repo_is_judged_by_that_repos_ci_runs_in_every_form():
    # the ledger tracks luis-mc/here (current folder); PR 85 of luis-mc/dev-standards is another project's
    for cmd in MERGE_FORMS:
        p = Project(ledger(trains=[train(pr=85, ci={'head_sha': 'x', 'state': 'running'})]))
        gh = p.stub_gh(view={'number': 85, 'headRefOid': 'abc'}, runs={'abc': OK_RUNS})
        expect_pass(bash(p, cmd, {'DELIVERY_GH': gh}))
        calls = gh_calls(p)
        assert any(c.startswith('pr view 85 --repo luis-mc/dev-standards') for c in calls), (cmd, calls)
        assert any(c.startswith('run list --repo luis-mc/dev-standards --commit abc') for c in calls), (cmd, calls)
        p.close()


@test
def dl06_foreign_repo_red_pending_or_missing_runs_deny():
    cases = {'pending': OK_RUNS + [{'status': 'in_progress', 'conclusion': None}],
             'failed': OK_RUNS + [{'status': 'completed', 'conclusion': 'failure'}],
             'no runs': []}
    for name, runs in cases.items():
        for cmd in (MERGE_FORMS[0], MERGE_FORMS[4]):
            p = Project(ledger(trains=[train(pr=85, ci={'head_sha': 'abc', 'state': 'success'})]))
            gh = p.stub_gh(view={'number': 85, 'headRefOid': 'abc'}, runs={'abc': runs})
            r = bash(p, cmd, {'DELIVERY_GH': gh})
            assert denied(r) and 'DL-06' in why(r) and 'luis-mc/dev-standards' in why(r), (name, cmd, r)
            p.close()
    # runs of an older head do not count for the current head
    p = Project(ledger())
    gh = p.stub_gh(view={'number': 85, 'headRefOid': 'newer'}, runs={'abc': OK_RUNS})
    assert denied(bash(p, MERGE_FORMS[0], {'DELIVERY_GH': gh}))
    p.close()


@test
def dl06_own_repo_flag_keeps_the_ledger_decision():
    p = Project(ledger(trains=[train(pr=85, ci={'head_sha': 'abc', 'state': 'success'})]))
    gh = p.stub_gh(view={'number': 85, 'headRefOid': 'abc'})       # no runs at all: the ledger decides
    for cmd in ('gh pr merge 85 -R luis-mc/here', 'gh pr merge https://github.com/luis-mc/here/pull/85'):
        expect_pass(bash(p, cmd, {'DELIVERY_GH': gh}))
    p.close()
    p = Project(ledger(trains=[train(pr=85, ci={'head_sha': 'old', 'state': 'running'})]))
    gh = p.stub_gh(view={'number': 85, 'headRefOid': 'abc'}, runs={'abc': OK_RUNS})
    assert denied(bash(p, 'gh pr merge 85 -R luis-mc/here', {'DELIVERY_GH': gh}))
    p.close()


@test
def gh_target_parser_forms():
    sys.path.insert(0, SCRIPTS)
    import hooklib
    t = hooklib.gh_target
    want = {'repo': 'a/b', 'number': 7, 'selector': '7'}
    for argv in (['gh', 'pr', 'merge', '7', '-R', 'a/b'], ['gh', 'pr', 'merge', '--repo', 'a/b', '7', '--squash'],
                 ['gh', 'pr', 'merge', '7', '--repo=a/b'], ['gh', 'pr', 'merge', '7', '-Ra/b'],
                 ['gh', 'pr', 'merge', '-b', 'text', '7', '-R', 'a/b']):
        assert t(argv) == want, (argv, t(argv))
    u = t(['gh', 'pr', 'merge', 'https://github.com/a/b/pull/7?x=1'])
    assert u['repo'] == 'a/b' and u['number'] == 7, u
    assert t(['gh', 'pr', 'merge', '7']) == {'repo': None, 'number': 7, 'selector': '7'}
    assert t(['gh', 'pr', 'merge', 'feature']) == {'repo': None, 'number': None, 'selector': 'feature'}


@test
def post_tool_merge_with_repo_flag_records_only_the_matching_train():
    sys.path.insert(0, SCRIPTS)
    import hook_post_tool as post
    assert post.pr_number(['gh', 'pr', 'merge', '85', '-R', 'a/b']) == 85
    assert post.pr_number(['gh', 'pr', 'merge', '-R', 'a/b', '85']) == 85
    assert post.pr_number(['gh', 'pr', 'merge', 'https://github.com/a/b/pull/85']) == 85
    p = Project(ledger(trains=[train(pr=85, repo='luis-mc/here', state='ci')]))
    data = {'tool_name': 'Bash', 'tool_input': {'command': 'gh pr merge 85 -R luis-mc/dev-standards'},
            'tool_response': {'stdout': 'ok'}}
    p.run('hook_post_tool.py', data)
    led = json.load(open(os.path.join(p.dir, '.delivery', 'ledger.json')))
    assert led['trains'][0]['state'] == 'ci', led['trains'][0]['state']
    data['tool_input']['command'] = 'gh pr merge 85 --repo luis-mc/here'
    p.run('hook_post_tool.py', data)
    led = json.load(open(os.path.join(p.dir, '.delivery', 'ledger.json')))
    assert led['trains'][0]['state'] == 'merged', led['trains'][0]['state']
    p.close()


@test
def dl07_checks_watch_denied():
    p = Project(ledger())
    assert 'DL-07' in why(bash(p, 'gh pr checks 5 --watch'))
    expect_pass(bash(p, 'gh pr checks 5'))
    p.close()


@test
def dl20_vercel_env_rm():
    p = Project(ledger())
    assert 'DL-20' in why(bash(p, 'vercel env rm FOO production'))
    expect_pass(bash(p, 'vercel env ls'))
    p.close()


@test
def dl23_unfrozen_installs():
    p = Project(ledger())
    assert 'DL-23' in why(bash(p, 'pnpm install --no-frozen-lockfile'))
    assert 'DL-23' in why(bash(p, 'cd app && npm install && python branch_gate.py'))
    expect_pass(bash(p, 'npm install left-pad'))              # not a gate context
    expect_pass(bash(p, 'pnpm install --frozen-lockfile && python branch_gate.py'))
    expect_pass(bash(p, 'npm ci'))
    p.close()


@test
def dl42_kill_by_name_and_stop_all():
    p = Project(ledger())
    for c in ('pkill node', 'taskkill /F /IM node.exe', 'killall python', 'docker stop $(docker ps -q)',
              'docker ps -q | xargs docker stop'):
        assert 'DL-42' in why(bash(p, c)), c
    expect_pass(bash(p, 'kill 4321'))
    expect_pass(bash(p, 'docker stop abc123'))
    expect_pass(bash(p, 'echo "pkill node"'))
    p.close()


@test
def dl53_worktree_outside_work_root():
    p = Project(ledger(), {'work_root': 'C:\\Work'})
    assert 'DL-53' in why(bash(p, 'git worktree add ../wt-x -b x'))
    assert 'DL-53' in why(bash(p, 'git worktree add C:\\Other\\wt'))
    expect_pass(bash(p, 'git worktree add C:\\Work\\wt-x -b x'))
    expect_pass(bash(p, 'git worktree add C:/Work/wt-y'))
    p.close()
    p = Project(ledger())                                      # no work_root: not checked
    expect_pass(bash(p, 'git worktree add ../wt-x'))
    p.close()


@test
def dl55_second_install_waits():
    inst = [{'product': 'app', 'state': 'installing', 'started': iso(10)}]
    p = Project(ledger(installs=inst))
    assert 'DL-55' in why(bash(p, 'schtasks /run /tn "AppUpdateNow"'))
    assert 'DL-55' in why(bash(p, 'msiexec /i app.msi'))
    p.close()
    p = Project(ledger(installs=[dict(inst[0], state='done')]))
    expect_pass(bash(p, 'msiexec /i app.msi'))
    p.close()
    p = Project(ledger(installs=[dict(inst[0], started=iso(300))]))      # stale
    expect_pass(bash(p, 'msiexec /i app.msi'))
    p.close()


@test
def dl73_outbound_send_from_config():
    p = Project(ledger())
    assert 'DL-73' in why(bash(p, 'gh issue comment 5 --body hi'))
    expect_pass(bash(p, 'gh pr view 5'))
    p.close()
    p = Project(ledger(), {'send_deny': ['curl -X POST']})
    assert 'DL-73' in why(bash(p, 'curl -X POST https://hooks.example/x'))
    expect_pass(bash(p, 'gh issue comment 5 --body hi'))
    p.close()


@test
def dl74_attribution_only_when_configured():
    cmd = 'git commit -m "fix\n\nCo-Authored-By: Claude <noreply@anthropic.com>"'
    p = Project(ledger())
    expect_pass(bash(p, cmd))
    p.close()
    p = Project(ledger(), {'no_attribution': True})
    assert 'DL-74' in why(bash(p, cmd))
    assert 'DL-74' in why(bash(p, 'gh pr create --title t --body "x\n\nGenerated with [Claude Code](https://claude.ai/code)"'))
    expect_pass(bash(p, 'git commit -m "fix the hook"'))
    expect_pass(bash(p, 'echo Co-Authored-By'))
    p.close()


# --- PreToolUse: Write -------------------------------------------------------------------------

@test
def dl75_md_outside_docs():
    p = Project(ledger())
    assert 'DL-75' in why(p.pre('Write', {'file_path': os.path.join(p.dir, 'notes.md')}))
    assert 'DL-75' in why(p.pre('Write', {'file_path': 'src/plan.md'}))
    for ok in ('docs/a.md', 'README.md', 'CLAUDE.md', '.claude/rules/x.md', 'src/code.py'):
        expect_pass(p.pre('Write', {'file_path': ok}))
    expect_pass(p.pre('Write', {'file_path': '/tmp/elsewhere/x.md'}))
    p.close()
    p = Project(ledger(), {'md_allow': ['CHANGELOG.md']})
    expect_pass(p.pre('Write', {'file_path': 'CHANGELOG.md'}))
    p.close()


# --- PreToolUse: launches ----------------------------------------------------------------------

BRIEF = 'Do the work. No UI change.\n```delivery\nsetup: 5\nwork: 10\nchecks: 5\neffort: medium\nowns:\n  - scripts/delivery/**\n```\n'


def local_agent(prompt=BRIEF, **kw):
    return dict({'prompt': prompt, 'model': 'sonnet', 'subagent_type': 'general-purpose'}, **kw)


@test
def d4_local_agent_needs_pc_bound_unless_cloud_full():
    p = Project(ledger())
    r = p.pre('Agent', local_agent())
    assert denied(r) and 'D4' in why(r), r
    expect_pass(p.pre('Agent', local_agent(BRIEF + 'PC-bound: needs the installed app\n'), {'DELIVERY_FREE_GB': '16'}))
    p.close()
    full = [agent(id='c%d' % i, owns=['x%d/' % i]) for i in range(2)]
    p = Project(ledger(agents=full), {'caps': {'cloud': 2, 'local': 3}})
    expect_pass(p.pre('Agent', local_agent(), {'DELIVERY_FREE_GB': '16'}))
    p.close()


def trigger(body_extra=None, **session):
    ctx = dict({'model': 'sonnet', 'effort_level': 'medium'}, **session)
    body = {'prompt': BRIEF, 'session_context': ctx}
    body.update(body_extra or {})
    return {'action': 'create', 'body': body}


@test
def dl36_37_model_effort_and_brief_markers():
    p = Project(ledger(), {'brief_markers': ['no push notifications', 'CRITICAL RUN RULE']})
    ok = trigger({'prompt': BRIEF + 'No push notifications. CRITICAL RUN RULE: push early.'})
    expect_pass(p.pre('RemoteTrigger', ok))
    r = p.pre('RemoteTrigger', trigger())
    assert denied(r) and 'DL-36' in why(r), r
    p.close()
    p = Project(ledger())
    r = p.pre('RemoteTrigger', {'action': 'create', 'body': {'prompt': BRIEF, 'session_context': {'effort_level': 'medium'}}})
    assert 'DL-37' in why(r) and 'model' in why(r), r
    r = p.pre('RemoteTrigger', {'action': 'create', 'body': {'prompt': BRIEF, 'session_context': {'model': 'sonnet'}}})
    assert 'DL-37' in why(r) and 'effort_level' in why(r), r
    expect_pass(p.pre('RemoteTrigger', {'action': 'list'}))
    r = p.pre('Agent', {'prompt': BRIEF + 'PC-bound: x\n'})
    assert 'DL-37' in why(r), r
    r = p.pre('Agent', {'prompt': 'PC-bound: x\nno block', 'model': 'sonnet'})
    assert 'DL-37' in why(r) and 'effort' in why(r), r
    p.close()


@test
def dl36_marker_lists_accept_the_ci_gate_path():
    p = Project(ledger(), {'brief_markers': ['BRIEF.md', ['one affected gate', 'CI is the gate']]})
    expect_pass(p.pre('RemoteTrigger', trigger({'prompt': BRIEF + 'BRIEF.md. One affected gate.'})))
    expect_pass(p.pre('RemoteTrigger', trigger({'prompt': BRIEF + 'BRIEF.md. CI is the gate: write CODE DONE.'})))
    r = p.pre('RemoteTrigger', trigger({'prompt': BRIEF + 'BRIEF.md only.'}))
    assert denied(r) and 'DL-36' in why(r) and 'one affected gate / CI is the gate' in why(r), r
    p.close()


@test
def dl38_caps():
    running = [agent(id='c%d' % i, owns=['x%d/' % i]) for i in range(3)]
    p = Project(ledger(agents=running), {'caps': {'cloud': 3, 'local': 3}})
    r = p.pre('RemoteTrigger', trigger())
    assert denied(r) and 'DL-38' in why(r), r
    p.close()
    loc = [agent(id='l%d' % i, where='local', owns=['y%d/' % i]) for i in range(3)]
    p = Project(ledger(agents=loc))
    r = p.pre('Agent', local_agent(BRIEF + 'PC-bound: app\n'), {'DELIVERY_FREE_GB': '16'})
    assert 'DL-38' in why(r) and 'local cap' in why(r), r
    p.close()
    p = Project(ledger())
    r = p.pre('Agent', local_agent(BRIEF + 'PC-bound: app\n'), {'DELIVERY_FREE_GB': '4'})
    assert 'DL-38' in why(r) and 'memory' in why(r), r
    p.close()
    sys.path.insert(0, SCRIPTS)
    import hooklib as _hl
    assert _hl.DEFAULTS['caps'] == {'cloud': 50, 'local': 3, 'total': 53}
    p = Project(ledger(agents=[agent(id='c%d' % i, owns=['x%d/' % i]) for i in range(50)]))   # default cloud cap 50
    r = p.pre('RemoteTrigger', trigger())
    assert denied(r) and 'DL-38' in why(r) and 'cloud cap' in why(r), r
    p.close()
    p = Project(ledger(agents=[agent(id='c%d' % i, owns=['x%d/' % i]) for i in range(19)]))
    expect_pass(p.pre('RemoteTrigger', trigger()))
    p.close()
    mixed = [agent(id='c%d' % i, owns=['x%d/' % i]) for i in range(2)] + \
            [agent(id='l%d' % i, where='local', owns=['y%d/' % i]) for i in range(2)]
    p = Project(ledger(agents=mixed), {'caps': {'cloud': 20, 'local': 3, 'total': 4}})      # total cap, config override
    r = p.pre('RemoteTrigger', trigger())
    assert denied(r) and 'DL-38' in why(r) and 'total cap' in why(r), r
    p.close()


@test
def dl41_owns_overlap():
    p = Project(ledger(agents=[agent(owns=['scripts/**'])]))
    r = p.pre('RemoteTrigger', trigger())
    assert denied(r) and 'DL-41' in why(r), r
    p.close()
    p = Project(ledger(agents=[agent(owns=['apps/web/**'])]))
    expect_pass(p.pre('RemoteTrigger', trigger()))
    p.close()
    p = Project(ledger(agents=[agent(owns=['scripts/delivery/join.py'], state='done')]))     # finished: free
    expect_pass(p.pre('RemoteTrigger', trigger()))
    p.close()


# --- PreToolUse: AskUserQuestion ----------------------------------------------------------------

def question(*texts):
    return {'questions': [{'question': t, 'header': 'Q', 'options': [{'label': 'a'}, {'label': 'b'}]} for t in texts]}


LONG = 'Should RELEASE-29 merge now, given that the smoke test of RELEASE-28 passed an hour ago and CI is green?'


@test
def q3_short_question_denied():
    p = Project(ledger())
    r = p.pre('AskUserQuestion', question(LONG, 'Merge?'))
    assert denied(r) and 'Q-3' in why(r), r
    expect_pass(p.pre('AskUserQuestion', question(LONG)))
    p.close()
    p = Project(ledger(), {'min_question_chars': 5})
    expect_pass(p.pre('AskUserQuestion', question('Merge?')))
    p.close()


@test
def q4_actionable_now_denies_dialog():
    p = Project(ledger(trains=[train(state='green', green_at=iso(30))]))
    r = p.pre('AskUserQuestion', question(LONG))
    assert denied(r) and 'Q-4' in why(r), r
    p.close()
    prev = train(id='T-1', release_no=28, state='merged', green_at=iso(9), merged_at=iso(8), cleaned_at=iso(7))
    p = Project(ledger(trains=[prev, train(id='T-2', release_no=29, state='joined')]))
    assert 'Q-4' in why(p.pre('AskUserQuestion', question(LONG)))
    p.close()
    p = Project(ledger(trains=[train(state='green', green_at=iso(30), hold={'reason': 'owner'})]))
    expect_pass(p.pre('AskUserQuestion', question(LONG)))
    p.close()


@test
def pre_hook_fails_open_on_bad_input():
    p = Project(ledger())
    p.write('.delivery/ledger.json', '{not json')
    expect_pass(bash(p, 'ls'))
    expect_pass(p.pre('Bash', {}))
    expect_pass(p.pre('Other', {}))
    p.close()


# --- SessionStart ---------------------------------------------------------------------------------

@test
def session_start_summary_catchup_and_watcher_prompt():
    lg = ledger(trains=[train(state='ci', pr=412)], agents=[agent(last_checked=iso(60))], watchers=[],
                installs=[{'product': 'app', 'state': 'installing', 'started': iso(3)}],
                publishes=[{'artifact': 'full-progress', 'last_at': iso(75)}])
    p = Project(lg)
    gh = p.stub_gh(merged=[{'number': 412, 'mergedAt': iso(4)}])
    r = p.run('hook_session_start.py', {}, {'DELIVERY_GH': gh})
    ctx = r[1]['hookSpecificOutput']['additionalContext']
    assert r[1]['hookSpecificOutput']['hookEventName'] == 'SessionStart'
    for needle in ('RELEASE-29', '1 running', 'DV1', 'app installing', 'published 75 min ago',
                   'merged at', 'cleanup.py --pr 412', 'hourly check-in', 'delivery_watch.py'):
        assert needle in ctx, (needle, ctx)
    p.close()


@test
def session_start_fresh_watcher_no_prompt_and_no_gh():
    p = Project(ledger())
    r = p.run('hook_session_start.py', {}, {'DELIVERY_GH': os.path.join(p.dir, 'missing.py')})
    ctx = r[1]['hookSpecificOutput']['additionalContext']
    assert 'start delivery_watch.py' not in ctx and 'Trains: none open' in ctx, ctx
    p.close()


# --- wiring ---------------------------------------------------------------------------------------

@test
def hooks_json_wires_every_script():
    with open(os.path.join(PLUGIN, 'hooks', 'hooks.json'), encoding='utf-8') as f:
        h = json.load(f)['hooks']
    def cmds(event):
        return [x['command'] for g in h[event] for x in g['hooks']]
    assert 'hook_stop.py' in cmds('Stop')[0]
    assert 'hook_session_start.py' in cmds('SessionStart')[0]
    pre = h['PreToolUse'][0]
    assert pre['matcher'] == 'Bash|PowerShell|Agent|Workflow|RemoteTrigger|AskUserQuestion|Write' and 'hook_pre_tool.py' in pre['hooks'][0]['command']
    for ev in ('PostToolUse', 'PostToolUseFailure'):
        assert h[ev][0]['matcher'] == 'Bash|Agent|RemoteTrigger|Artifact|AskUserQuestion'
        assert 'hook_post_tool.py' in h[ev][0]['hooks'][0]['command']
    assert 'hook_post_tool.py' in cmds('UserPromptSubmit')[0]
    for ev in h:
        for c in cmds(ev):
            assert c.startswith('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/') and '|| python "' in c, c


@test
def hooks_never_write_the_ledger():
    p = Project(ledger(trains=[train(state='green', green_at=iso(30))]))
    path = os.path.join(p.dir, '.delivery', 'ledger.json')
    before = open(path).read()
    p.stop('x')
    p.pre('AskUserQuestion', question(LONG))
    p.run('hook_session_start.py', {})
    assert open(path).read() == before
    p.close()


def main():
    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
            passed += 1
        except Exception:
            failed += 1
            print('FAIL %s' % fn.__name__)
            traceback.print_exc()
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
