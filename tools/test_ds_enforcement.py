#!/usr/bin/env python3
"""Tests for the design-system enforcement kit (DSY99 draft).

Covers: the kit templates of luismc-docs (copied by `design_system.py guards --stack typescript-vitest-kit`,
self-tested with plain Node through a small vitest stand-in), the edit-time hook of luismc-delivery
(`hook_design_edit.py`) and the plan-rows check of luismc-artifacts (`plan_rows_check.py`).

Run: python -I tools/test_ds_enforcement.py
Standard library only (the Node self-tests are skipped when Node 22.6 or later is not on PATH).
Prints "N passed, 0 failed" and exits 0 when all pass.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PLUGINS = os.path.join(REPO, 'claude', 'plugins')
KIT = os.path.join(PLUGINS, 'docs', 'templates', 'design-system', 'guards', 'typescript-vitest-kit')
SHIM = os.path.join(HERE, 'fixtures', 'vitest_shim', 'run.mjs')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    return mod


DS = load(os.path.join(PLUGINS, 'docs', 'scripts', 'design_system.py'), 'design_system')
HOOK = load(os.path.join(PLUGINS, 'delivery', 'scripts', 'hook_design_edit.py'), 'hook_design_edit')
ROWS = load(os.path.join(PLUGINS, 'artifacts', 'scripts', 'plan_rows_check.py'), 'plan_rows_check')

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def node_ok():
    exe = shutil.which('node')
    if not exe:
        return False
    out = subprocess.run([exe, '--version'], capture_output=True, text=True).stdout.strip()
    m = re.match(r'v(\d+)\.(\d+)', out)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (22, 6)


# --- kit templates ---------------------------------------------------------------------

@test
def kit_is_copied_by_the_guards_command():
    d = tempfile.mkdtemp()
    try:
        assert DS.main(['guards', '--stack', 'typescript-vitest-kit', '--root', d]) == 0
        assert not os.path.exists(os.path.join(d, 'scripts', 'design'))  # dry run
        assert DS.main(['guards', '--stack', 'typescript-vitest-kit', '--root', d, '--apply']) == 0
        for n in ('no-app-css-scan.ts', 'no-app-css.test.ts', 'no-app-css.known.json', 'layout.known.json',
                  'wizard-behaviour.known.json', 'dom-layout.ts',
                  'dom-layout-judge.test.ts', 'dom-layout-example.spec.ts', 'wizard-behaviour.ts',
                  'wizard-behaviour.test.ts', 'raw-controls-scan.ts', 'raw-controls.test.ts',
                  'raw-controls.known.json', 'contrast.ts', 'contrast.test.ts', 'contrast.known.json', 'README.md'):
            assert os.path.isfile(os.path.join(d, 'scripts', 'design', n)), n
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def new_files_name_no_other_project():
    bad = ('twin', 'master', 'operator')
    files = []
    for base in (KIT,):
        files += [os.path.join(base, n) for n in os.listdir(base)]
    files.append(os.path.join(PLUGINS, 'docs', 'templates', 'ui-brief-checklist.md'))
    files.append(os.path.join(PLUGINS, 'delivery', 'references', 'design-gate.md'))
    for f in files:
        t = open(f, encoding='utf-8').read().lower()
        for w in bad:
            assert w not in t, '%s: %s' % (os.path.basename(f), w)


@test
def known_list_starts_empty_and_is_valid_json():
    data = json.load(open(os.path.join(KIT, 'no-app-css.known.json'), encoding='utf-8'))
    assert data['entries'] == []
    for n in ('layout.known.json', 'wizard-behaviour.known.json', 'raw-controls.known.json', 'contrast.known.json'):
        d2 = json.load(open(os.path.join(KIT, n), encoding='utf-8'))
        assert d2['entries'] == [], n


@test
def breach_constants_are_read_from_json_not_typed_in_ts():
    for ts, const, js in (('dom-layout.ts', 'KNOWN_LAYOUT_BREACHES', 'layout.known.json'),
                          ('wizard-behaviour.ts', 'WIZARD_BEHAVIOUR_TO_FIX', 'wizard-behaviour.known.json')):
        t = open(os.path.join(KIT, ts), encoding='utf-8').read()
        assert js in t and 'readFileSync' in t, ts
        assert not re.search(r'export const %s[^=]*=\s*\[' % const, t), ts


@test
def kit_self_tests_pass_under_node():
    if not node_ok():
        print('  (skipped: Node 22.6 or later not found)')
        return
    d = tempfile.mkdtemp()
    try:
        dest = os.path.join(d, 'scripts', 'design')
        shutil.copytree(KIT, dest)
        names = ['no-app-css.test.ts', 'dom-layout-judge.test.ts', 'wizard-behaviour.test.ts',
                 'raw-controls.test.ts', 'contrast.test.ts']
        r = subprocess.run(['node', SHIM] + names, cwd=dest, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        assert ' 0 failed' in r.stdout, r.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def no_app_css_scan_finds_a_planted_breach_in_a_tree():
    if not node_ok():
        print('  (skipped: Node 22.6 or later not found)')
        return
    d = tempfile.mkdtemp()
    try:
        dest = os.path.join(d, 'scripts', 'design')
        shutil.copytree(KIT, dest)
        os.makedirs(os.path.join(d, 'apps', 'web'))
        os.makedirs(os.path.join(d, 'packages', 'ui', 'src'))
        open(os.path.join(d, 'apps', 'web', 'a.css'), 'w').write('.a{}')
        r = subprocess.run(['node', SHIM, 'no-app-css.test.ts'], cwd=dest, capture_output=True, text=True, timeout=120)
        assert r.returncode == 1, r.stdout + r.stderr  # a new breach not on the list fails
        assert 'new stylesheet breach' in r.stdout, r.stdout
        known = {'entries': [{'file': 'apps/web/a.css', 'kind': 'stylesheet', 'count': 1, 'task': 'T1'}]}
        json.dump(known, open(os.path.join(dest, 'no-app-css.known.json'), 'w'))
        r = subprocess.run(['node', SHIM, 'no-app-css.test.ts'], cwd=dest, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr  # listed: green
        os.remove(os.path.join(d, 'apps', 'web', 'a.css'))
        r = subprocess.run(['node', SHIM, 'no-app-css.test.ts'], cwd=dest, capture_output=True, text=True, timeout=120)
        assert r.returncode == 1 and 'known 1, now 0' in r.stdout, r.stdout  # fixed but still listed: fails
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- edit-time hook --------------------------------------------------------------------

def project_with_ds(config=None):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, 'docs', 'design-system'))
    os.makedirs(os.path.join(d, 'apps', 'web', 'src'))
    os.makedirs(os.path.join(d, 'packages', 'ui', 'src'))
    if config is not None:
        os.makedirs(os.path.join(d, '.delivery'))
        json.dump(config, open(os.path.join(d, '.delivery', 'config.json'), 'w'))
    return d


def edit(d, rel, new, tool='Edit'):
    key = 'content' if tool == 'Write' else 'new_string'
    return {'tool_name': tool, 'cwd': d, 'tool_input': {'file_path': os.path.join(d, rel), key: new}}


@test
def hook_warns_on_css_and_hand_made_parts_in_app_code():
    d = project_with_ds()
    try:
        for text in ('<button onClick={go}>Go</button>', '<table><tr/></table>', '<div role="tablist"/>',
                     '<i style={{ width: 4 }} />', 'const A = styled.div`x`', '<progress value="1"/>'):
            msg = HOOK.decide(edit(d, 'apps/web/src/a.tsx', text))
            assert msg and 'Design system' in msg, text
        assert HOOK.decide(edit(d, 'apps/web/src/x.css', '.a{}', 'Write'))
        multi = {'tool_name': 'MultiEdit', 'cwd': d, 'tool_input': {
            'file_path': os.path.join(d, 'apps/web/src/a.tsx'), 'edits': [{'new_string': 'ok'}, {'new_string': '<table>'}]}}
        assert HOOK.decide(multi)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def hook_stays_quiet_for_clean_edits_shared_ui_and_other_projects():
    d = project_with_ds()
    try:
        assert HOOK.decide(edit(d, 'apps/web/src/a.tsx', '<Button kind="primary">Go</Button>')) is None
        assert HOOK.decide(edit(d, 'apps/web/src/a.tsx', '<i style={{ "--w": w }} />')) is None
        assert HOOK.decide(edit(d, 'packages/ui/src/Button.tsx', '<button>Go</button>')) is None  # shared UI may
        assert HOOK.decide(edit(d, 'docs/notes.md', '<button>')) is None
        assert HOOK.decide({'tool_name': 'Read', 'tool_input': {'file_path': os.path.join(d, 'apps/a.tsx')}}) is None
    finally:
        shutil.rmtree(d, ignore_errors=True)
    other = tempfile.mkdtemp()  # no docs/design-system/: the hook is off
    try:
        os.makedirs(os.path.join(other, 'apps'))
        assert HOOK.decide(edit(other, 'apps/a.tsx', '<button>')) is None
    finally:
        shutil.rmtree(other, ignore_errors=True)


@test
def hook_reads_app_paths_from_the_config_and_prints_json():
    d = project_with_ds({'design_system': {'app_paths': ['web/'], 'shared_paths': ['kit/']}})
    try:
        os.makedirs(os.path.join(d, 'web'))
        assert HOOK.decide(edit(d, 'web/a.tsx', '<button>')) is not None
        assert HOOK.decide(edit(d, 'apps/web/src/a.tsx', '<button>')) is None  # no longer an app path
        r = subprocess.run([sys.executable, '-I', os.path.join(PLUGINS, 'delivery', 'scripts', 'hook_design_edit.py')],
                           input=json.dumps(dict(edit(d, 'web/a.tsx', '<button>'), session_id='cfg')), capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE_DESIGN_EDIT_STATE_DIR=d))
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out['hookSpecificOutput']['hookEventName'] == 'PreToolUse'
        assert 'permissionDecision' not in out['hookSpecificOutput']  # first breach: a warning only
        assert 'additionalContext' in out['hookSpecificOutput']
        r = subprocess.run([sys.executable, '-I', os.path.join(PLUGINS, 'delivery', 'scripts', 'hook_design_edit.py')],
                           input='not json', capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == ''  # never blocks, never crashes
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def hook_first_breach_has_no_permission_decision_and_repeat_is_denied():
    d = project_with_ds()
    st = tempfile.mkdtemp()
    try:
        os.environ['CLAUDE_DESIGN_EDIT_STATE_DIR'] = st
        data = dict(edit(d, 'apps/web/src/a.tsx', '<table>'), session_id='k1')
        first = HOOK.respond(data)['hookSpecificOutput']
        assert 'permissionDecision' not in first and first['hookEventName'] == 'PreToolUse' and 'additionalContext' in first
        assert HOOK.respond(data)['hookSpecificOutput']['permissionDecision'] == 'deny'
    finally:
        os.environ.pop('CLAUDE_DESIGN_EDIT_STATE_DIR', None)
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(st, ignore_errors=True)


@test
def hook_judges_what_an_edit_adds_not_the_whole_text():
    d = project_with_ds()
    try:
        old = '<button onClick={a}>Save</button> {count}'
        new = '<button onClick={a}>Save</button> {total}'
        data = edit(d, 'apps/web/src/a.tsx', new)
        data['tool_input']['old_string'] = old
        assert HOOK.decide(data) is None  # a rename next to an old button
        data['tool_input']['new_string'] = new + ' <button>Two</button>'
        assert HOOK.decide(data)  # a new button still warns
        multi = {'tool_name': 'MultiEdit', 'cwd': d, 'tool_input': {'file_path': os.path.join(d, 'apps/web/src/a.tsx'),
                 'edits': [{'old_string': old, 'new_string': new}]}}
        assert HOOK.decide(multi) is None
        # Write over an existing file: only the increase counts
        f = os.path.join(d, 'apps/web/src/b.tsx')
        open(f, 'w').write('<table></table>')
        assert HOOK.decide(edit(d, 'apps/web/src/b.tsx', '<table></table> x', 'Write')) is None
        assert HOOK.decide(edit(d, 'apps/web/src/b.tsx', '<table></table><table></table>', 'Write'))
        # test files never warn
        for rel in ('apps/web/src/a.test.tsx', 'apps/web/src/a.spec.ts', 'apps/web/__tests__/a.tsx', 'apps/web/tests/a.tsx'):
            assert HOOK.decide(edit(d, rel, '<button>x</button>')) is None, rel
        # an Edit to an existing stylesheet does not warn; a new one does
        open(os.path.join(d, 'apps/web/src/x.css'), 'w').write('.a{}')
        assert HOOK.decide(edit(d, 'apps/web/src/x.css', '.a{color:red}')) is None
        assert HOOK.decide(edit(d, 'apps/web/src/y.css', '.a{}', 'Write'))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- plan rows check -------------------------------------------------------------------

PLAN = """# Plan

| # | Change | Hours |
|---|---|---|
| 1 | **One engine** for wizards | 29 |
| 2 | Behaviour guard | 18 |
| 3 | Source scans | 9 |

## Not proposed

| 9 | A screenshot gate | 0 |

## Findings

1. First finding
2) Second finding
| B07 | Start again is missing | x |
"""


@test
def plan_rows_are_found_with_keys_and_skipped_sections():
    rows = ROWS.find_rows(PLAN, 'P1')
    keys = [r['key'] for r in rows]
    assert 'P1#9' not in keys  # the "Not proposed" section is skipped
    assert keys.count('P1#1') == 1  # a repeated id counts once
    assert 'P1#B07' in keys and 'P1#3' in keys
    assert rows[0]['text'] == 'One engine for wizards'


@test
def plan_rows_count_only_under_plan_like_headings():
    status = "# Report\n\n## Done\n\n1. Lint kit ...: done.\n2. Tests: done.\n3. Docs: done.\n4. Hook: done.\n"
    assert ROWS.find_rows(status, 'R') == []
    prop = "## Proposed changes\n\n1. One\n2. Two\n\n### Detail\n\n3. Not a row\n\n## Not proposed\n\n4. Dropped\n"
    assert [r['key'] for r in ROWS.find_rows(prop, 'R')] == ['R#1', 'R#2']
    assert [r['key'] for r in ROWS.find_rows("### findings (audit)\n\n| B07 | x |\n", 'R')] == ['R#B07']


@test
def plan_rows_tag_comes_from_the_folder_for_generic_names():
    from pathlib import Path
    assert ROWS.tag_for(Path('docs/work/DSY97/plan.md')) == 'DSY97'
    assert ROWS.tag_for(Path('docs/work/DSY97-report.md')) == 'DSY97-report'


def run_check(tasks, extra=None):
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, 'docs', 'artifacts'))
        json.dump({'spec': 'x', 'tasks': tasks}, open(os.path.join(d, 'docs', 'artifacts', 'registry.json'), 'w'))
        rep = os.path.join(d, 'P1.md')
        open(rep, 'w', encoding='utf-8').write(PLAN)
        reg = os.path.join(d, 'docs', 'artifacts', 'registry.json')
        return subprocess.run([sys.executable, '-I', os.path.join(PLUGINS, 'artifacts', 'scripts', 'plan_rows_check.py'),
                               rep, '--registry', reg] + (extra or []), capture_output=True, text=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def plan_rows_without_a_task_fail_the_check():
    r = run_check([{'id': 'T1', 'item': 'x', 'detail': 'P1#1 and P1#2'}], ['--commands'])
    assert r.returncode == 1, r.stdout + r.stderr
    assert 'P1#3' in r.stdout and 'P1#B07' in r.stdout and 'P1#1:' not in r.stdout
    assert 'task-add --owner project' in r.stdout


@test
def plan_rows_all_tasked_pass_and_a_bad_registry_is_a_usage_error():
    tasks = [{'id': 'T%d' % i, 'item': 'x', 'detail': k} for i, k in enumerate(['P1#1', 'P1#2', 'P1#3', 'P1#B07'])]
    r = run_check(tasks)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, '-I', os.path.join(PLUGINS, 'artifacts', 'scripts', 'plan_rows_check.py'),
                        __file__, '--registry', os.path.join(tempfile.gettempdir(), 'nope-registry.json')],
                       capture_output=True, text=True)
    assert r.returncode == 2


# --- wiring ----------------------------------------------------------------------------

@test
def the_edit_hook_is_wired_for_pre_tool_use_and_resets_each_turn():
    hooks = json.load(open(os.path.join(PLUGINS, 'delivery', 'hooks', 'hooks.json'), encoding='utf-8'))['hooks']
    pre = [h for h in hooks['PreToolUse'] if 'hook_design_edit' in json.dumps(h)]
    assert len(pre) == 1 and pre[0]['matcher'] == 'Edit|MultiEdit|Write'
    assert not any('hook_design_edit' in json.dumps(h) for h in hooks['PostToolUse'])
    for ev in ('UserPromptSubmit', 'Stop'):
        assert any('hook_design_edit' in json.dumps(h) for h in hooks[ev]), ev


@test
def hook_first_breach_warns_and_a_repeat_in_the_same_turn_denies():
    d = project_with_ds()
    st = tempfile.mkdtemp()
    os.environ['CLAUDE_DESIGN_EDIT_STATE_DIR'] = st
    try:
        bad = edit(d, 'apps/web/src/a.tsx', '<button>Go</button>')
        bad['session_id'] = 's1'
        first = HOOK.respond(dict(bad))['hookSpecificOutput']
        assert 'permissionDecision' not in first and 'Warning' in first['additionalContext']
        second = HOOK.respond(dict(bad))['hookSpecificOutput']
        assert second['permissionDecision'] == 'deny' and 'repeat' in second['permissionDecisionReason']
        clean = edit(d, 'apps/web/src/a.tsx', '<Button/>')
        clean['session_id'] = 's1'
        assert HOOK.respond(dict(clean)) is None  # clean edits never count
        other = dict(bad, session_id='s2')
        assert HOOK.respond(other)['hookSpecificOutput'].get('permissionDecision') is None  # another session
        # a new turn (prompt or stop) clears the count
        assert HOOK.respond({'hook_event_name': 'UserPromptSubmit', 'session_id': 's1'}) is None
        assert HOOK.respond(dict(bad))['hookSpecificOutput'].get('permissionDecision') is None
        assert HOOK.respond(dict(bad))['hookSpecificOutput']['permissionDecision'] == 'deny'
        assert HOOK.respond({'hook_event_name': 'Stop', 'session_id': 's1'}) is None
        assert HOOK.respond(dict(bad))['hookSpecificOutput'].get('permissionDecision') is None
    finally:
        os.environ.pop('CLAUDE_DESIGN_EDIT_STATE_DIR', None)
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(st, ignore_errors=True)


@test
def hook_denies_through_the_process_with_json_on_stdout():
    d = project_with_ds()
    st = tempfile.mkdtemp()
    try:
        env = dict(os.environ, CLAUDE_DESIGN_EDIT_STATE_DIR=st)
        payload = dict(edit(d, 'apps/web/src/a.tsx', '<table>'), session_id='p1')
        script = os.path.join(PLUGINS, 'delivery', 'scripts', 'hook_design_edit.py')
        outs = [subprocess.run([sys.executable, '-I', script], input=json.dumps(payload), capture_output=True, text=True, env=env)
                for _ in range(2)]
        assert [json.loads(o.stdout)['hookSpecificOutput'].get('permissionDecision') for o in outs] == [None, 'deny']
        assert all(o.returncode == 0 for o in outs)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(st, ignore_errors=True)


@test
def config_schema_types_the_design_system_paths():
    sys.path.insert(0, os.path.join(PLUGINS, 'delivery', 'scripts'))
    import delivery_config as C
    assert C.validate_config({'design_system': {'app_paths': ['apps/'], 'shared_paths': ['packages/ui/']}}) == ([], [])
    errors, _ = C.validate_config({'design_system': {'app_paths': 'apps/', 'shared_paths': ['']}})
    assert len(errors) == 2, errors
    errors, warnings = C.validate_config({'design_system': {'app_path': ['x']}})
    assert errors == [] and any('app_path' in w for w in warnings)  # a misspelt key warns


# --- brief checklist block ---------------------------------------------------------------

@test
def brief_writes_a_marked_block_and_is_idempotent():
    d = tempfile.mkdtemp()
    try:
        open(os.path.join(d, 'AGENTS.md'), 'w', encoding='utf-8', newline='').write('# Agents\n\nRules.\n')
        assert DS.main(['brief', '--root', d]) == 0  # dry run
        assert open(os.path.join(d, 'AGENTS.md'), encoding='utf-8', newline='').read() == '# Agents\n\nRules.\n'
        assert not os.path.exists(os.path.join(d, '.github'))
        assert DS.main(['brief', '--root', d, '--apply']) == 0
        agents = open(os.path.join(d, 'AGENTS.md'), encoding='utf-8', newline='').read()
        pr = open(os.path.join(d, '.github', 'pull_request_template.md'), encoding='utf-8', newline='').read()
        for text in (agents, pr):
            assert text.count(DS.BRIEF_START) == 1 and text.count(DS.BRIEF_END) == 1
            assert 'Design system checklist' in text and 'Paste into the UI task brief' not in text
        assert agents.startswith('# Agents\n\nRules.\n\n')
        assert DS.main(['brief', '--root', d, '--apply']) == 0
        assert open(os.path.join(d, 'AGENTS.md'), encoding='utf-8', newline='').read() == agents  # second run: no change
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def brief_refreshes_a_stale_block_and_keeps_the_text_around_it():
    block = DS.brief_block()
    stale = 'before\n\n' + DS.BRIEF_START + '\nold text\n' + DS.BRIEF_END + '\n\nafter\n'
    fresh = DS.brief_update(stale, block)
    assert fresh == 'before\n\n' + block + '\n\nafter\n'
    assert DS.brief_update(fresh, block) == fresh


# --- known list growth (change_notes.py) ---------------------------------------------------

CN_DIR = os.path.join(PLUGINS, 'delivery', 'templates', 'shared', 'scripts', 'delivery')


def git(d, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'commit.gpgsign=false',
                           '-c', 'core.autocrlf=false'] + list(args), cwd=d, capture_output=True, text=True, env=env)


def known_repo(entries_main):
    d = tempfile.mkdtemp()
    git(d, 'init', '-q', '-b', 'main')
    os.makedirs(os.path.join(d, 'scripts', 'delivery'))
    for n in ('delivery_common.py', 'change_notes.py'):
        shutil.copyfile(os.path.join(CN_DIR, n), os.path.join(d, 'scripts', 'delivery', n))
    json.dump({'specs': ['docs/specs/*.md']}, open(os.path.join(d, 'notes.json'), 'w'))
    os.makedirs(os.path.join(d, 'scripts', 'design'))
    if entries_main is not None:
        write_known(d, entries_main)
    git(d, 'add', '-A')
    git(d, 'commit', '-q', '-m', 'base')
    git(d, 'checkout', '-q', '-b', 't1-work')
    return d


def write_known(d, entries, name='no-app-css.known.json'):
    json.dump({'entries': entries}, open(os.path.join(d, 'scripts', 'design', name), 'w'))


def run_notes(d):
    r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'delivery', 'change_notes.py'), 'check',
                        '--config', 'notes.json', '--base-ref', 'main'], cwd=d, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    return r.returncode, r.stdout + r.stderr


def commit_all(d):
    git(d, 'add', '-A')
    git(d, 'commit', '-q', '-m', 'work')


A = {'file': 'apps/a.css', 'kind': 'stylesheet', 'count': 2, 'task': 'T1'}
B = {'file': 'apps/b.css', 'kind': 'stylesheet', 'count': 1, 'task': 'T2'}


@test
def a_diff_that_adds_a_known_list_entry_or_raises_a_count_fails():
    d = known_repo([A])
    try:
        write_known(d, [A, B])
        commit_all(d)
        rc, out = run_notes(d)
        assert rc == 1 and 'apps/b.css' in out and 'only shrinks' in out, out
        write_known(d, [dict(A, count=3)])
        commit_all(d)
        rc, out = run_notes(d)
        assert rc == 1 and 'raised' in out, out
    finally:
        shutil.rmtree(d, ignore_errors=True)


LB = {'screen': 'home', 'width': 360, 'rule': 'gap', 'task': 'T3'}
WB = {'wizard': 'import', 'state': 'running', 'rule': 'busy-not-disabled', 'task': 'T4'}


@test
def the_growth_guard_covers_the_layout_and_wizard_lists():
    for name, entry in (('layout.known.json', LB), ('wizard-behaviour.known.json', WB)):
        d = known_repo(None)
        try:
            write_known(d, [entry], name)  # the install change: new at the base
            git(d, 'add', '-A')
            git(d, 'commit', '-q', '-m', 'base2')
            git(d, 'branch', '-f', 'main', 'HEAD')
            write_known(d, [entry, dict(entry, task='T9')], name)  # a raised (new) entry
            commit_all(d)
            rc, out = run_notes(d)
            assert rc == 1 and name in out and 'only shrinks' in out, (name, out)
            write_known(d, [dict(entry, count=2)], name)  # a raised count
            commit_all(d)
            rc, out = run_notes(d)
            assert rc == 1 and name in out, (name, out)
            write_known(d, [], name)  # shrinking passes
            commit_all(d)
            rc, out = run_notes(d)
            assert rc == 0, (name, out)
        finally:
            shutil.rmtree(d, ignore_errors=True)


@test
def shrinking_a_known_list_and_the_install_change_pass():
    d = known_repo([A, B])
    try:
        write_known(d, [dict(A, count=1)])  # lower a count, drop an entry
        commit_all(d)
        rc, out = run_notes(d)
        assert rc == 0, out
    finally:
        shutil.rmtree(d, ignore_errors=True)
    d = known_repo(None)  # the list is new at the base: this branch installs it with today's breaches
    try:
        write_known(d, [A, B])
        commit_all(d)
        rc, out = run_notes(d)
        assert rc == 0, out
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def the_known_list_globs_are_configurable():
    d = known_repo([A])
    try:
        json.dump({'specs': ['docs/specs/*.md'], 'known_lists': ['other/*.json']}, open(os.path.join(d, 'notes.json'), 'w'))
        git(d, 'add', '-A')
        git(d, 'commit', '-q', '-m', 'config')
        git(d, 'branch', '-f', 'main', 'HEAD')
        write_known(d, [A, B])
        commit_all(d)
        rc, out = run_notes(d)
        assert rc == 0, out  # no longer a known list
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- plan rows in the Stop hook ---------------------------------------------------------------

def stop_module():
    sys.path.insert(0, os.path.join(PLUGINS, 'artifacts', 'scripts'))
    return load(os.path.join(PLUGINS, 'artifacts', 'scripts', 'hook_end_of_turn.py'), 'hook_end_of_turn')


def plan_project(tasks, name='plan.md', folder='P1'):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, 'docs', 'artifacts'))
    json.dump({'spec': 'x', 'tasks': tasks}, open(os.path.join(d, 'docs', 'artifacts', 'registry.json'), 'w'))
    os.makedirs(os.path.join(d, 'docs', 'work', folder))
    open(os.path.join(d, 'docs', 'work', folder, name), 'w', encoding='utf-8').write(PLAN)
    return d


@test
def the_stop_hook_finds_untasked_rows_of_a_fresh_report_and_remembers_clean_ones():
    S = stop_module()
    d = plan_project([{'id': 'T1', 'item': 'x', 'detail': 'P1#1 P1#2'}])
    try:
        rows = S.plan_untasked(d, {}, 's1')
        keys = sorted(r['key'] for r in rows)
        assert keys == ['P1#3', 'P1#B07'], keys
        assert all(r['report'] == 'docs/work/P1/plan.md' for r in rows)
        reason = S.build_plan_reason('/x/project_artifacts.py', rows)
        assert 'P1#3' in reason and 'task-add' in reason and '<tag>#<id>' in reason
        assert S.fingerprint([], [], plan=rows) != S.fingerprint([], [])
        assert 'P1#3' in S.describe([], [], plan=rows)
        # tasking every row makes the next stop clean; the clean report is remembered in the stop state
        json.dump({'spec': 'x', 'tasks': [{'id': 'T%d' % i, 'item': 'x', 'detail': k}
                                          for i, k in enumerate(['P1#1', 'P1#2', 'P1#3', 'P1#B07'])]},
                  open(os.path.join(d, 'docs', 'artifacts', 'registry.json'), 'w'))
        assert S.plan_untasked(d, {}, 's1') == []
        state = json.load(open(os.path.join(d, S.STATE_NAME), encoding='utf-8'))
        assert 'docs/work/P1/plan.md' in state['plan:s1']
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def the_stop_hook_ignores_briefs_old_reports_and_unreadable_registries():
    S = stop_module()
    d = plan_project([], name='BRIEF.md')
    try:
        assert S.plan_untasked(d, {}, 's1') == []  # a brief is not a report
    finally:
        shutil.rmtree(d, ignore_errors=True)
    d = plan_project([])
    try:
        old = os.path.join(d, 'docs', 'work', 'P1', 'plan.md')
        os.utime(old, (1, 1))  # written long ago, not in this turn
        assert S.plan_untasked(d, {}, 's1') == []
        os.utime(old, None)
        assert S.plan_untasked(d, {}, 's1') != []
        os.remove(os.path.join(d, 'docs', 'artifacts', 'registry.json'))
        assert S.plan_untasked(d, {}, 's2') == []  # unreadable registry: fail open
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def a_report_of_an_earlier_turn_does_not_block_and_one_of_this_turn_does():
    S = stop_module()
    d = plan_project([])
    try:
        rep = os.path.join(d, 'docs', 'work', 'P1', 'plan.md')
        now = time.time()
        os.utime(rep, (now - 600, now - 600))        # written 10 minutes ago, within the old 2 h window
        os.makedirs(os.path.join(d, '.claude'), exist_ok=True)
        with open(os.path.join(d, S.STATE_NAME), 'w', encoding='utf-8') as f:
            json.dump({'turn:s1': {'start': now - 60}}, f)
        assert S.plan_untasked(d, {}, 's1') == []   # an earlier turn: not looked at
        assert S.plan_untasked(d, {}, 's2') != []   # another session has no stamp: the 2 h fallback sees it
        os.utime(rep, (now, now))                    # changed in this turn
        rows = S.plan_untasked(d, {}, 's1')
        assert sorted(r['key'] for r in rows) == ['P1#1', 'P1#2', 'P1#3', 'P1#B07'], rows
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def without_a_turn_stamp_the_two_hour_window_still_applies():
    S = stop_module()
    d = plan_project([])
    try:
        rep = os.path.join(d, 'docs', 'work', 'P1', 'plan.md')
        assert S.turn_start({}, 's1') is None
        assert S.turn_start({'turn:s1': {'start': 'x'}}, 's1') is None
        assert S.turn_start({'turn:s1': {'start': True}}, 's1') is None
        assert S.plan_untasked(d, {}, 's1') != []
        old = time.time() - 3 * 3600
        os.utime(rep, (old, old))
        assert S.plan_untasked(d, {}, 's1') == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def the_turn_start_hook_stamps_the_session_and_is_wired_on_user_prompt_submit():
    hooks = json.load(open(os.path.join(PLUGINS, 'artifacts', 'hooks', 'hooks.json'), encoding='utf-8'))
    cmds = [h['command'] for g in hooks['hooks']['UserPromptSubmit'] for h in g['hooks']]
    assert any('hook_turn_start.py' in c for c in cmds), cmds
    d = plan_project([])
    try:
        git(d, 'init', '-q', '-b', 'main')
        script = os.path.join(PLUGINS, 'artifacts', 'scripts', 'hook_turn_start.py')
        before = time.time()
        r = subprocess.run([sys.executable, '-I', script], input=json.dumps({'session_id': 's9', 'cwd': d}),
                           capture_output=True, text=True, cwd=d)
        assert r.returncode == 0, r.stderr
        state = json.load(open(os.path.join(d, '.claude', 'artifacts-stop-state.json'), encoding='utf-8'))
        assert before - 1 <= state['turn:s9']['start'] <= time.time() + 1, state
        r = subprocess.run([sys.executable, '-I', script], input=json.dumps({'session_id': 's9', 'cwd': d}),
                           capture_output=True, text=True, cwd=d, env=dict(os.environ, CLAUDE_ARTIFACTS_HOOKS='off'))
        assert r.returncode == 0 and r.stdout == ''
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- wizard states are required in the shipped harness ----------------------------------------

@test
def the_harness_source_requires_the_ten_states_and_the_readme_names_the_stack():
    src = open(os.path.join(KIT, 'wizard-behaviour.ts'), encoding='utf-8').read()
    for s in ('loading', 'first-run', 'planning', 'ready-to-review', 'running', 'paused', 'stopped', 'failed', 'done', 'done-after-reload'):
        assert "'%s'" % s in src, s
    assert 'never drop one' in src and 'droppedStates' in src
    readme = open(os.path.join(KIT, 'README.md'), encoding='utf-8').read()
    assert 'TypeScript with Vitest only' in readme


@test
def the_delivery_spec_maps_the_gate_reference_and_the_specs_carry_the_new_ids():
    spec = open(os.path.join(REPO, 'docs', 'features', 'delivery', 'spec.md'), encoding='utf-8').read()
    assert 'claude/plugins/delivery/references/design-gate.md' in spec
    assert '| DL-92 |' in open(os.path.join(REPO, 'docs', 'architecture', 'DELIVERYSPEC.md'), encoding='utf-8').read()
    assert '**R15.9**' in open(os.path.join(PLUGINS, 'docs', 'references', 'docspec.md'), encoding='utf-8').read()


def main():
    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
            passed += 1
        except Exception:  # noqa: BLE001
            failed += 1
            print('FAIL %s' % fn.__name__)
            traceback.print_exc()
    print('%d passed, %d failed' % (passed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
