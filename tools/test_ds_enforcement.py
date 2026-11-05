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
        for n in ('no-app-css-scan.ts', 'no-app-css.test.ts', 'no-app-css.known.json', 'dom-layout.ts',
                  'dom-layout-judge.test.ts', 'dom-layout-example.spec.ts', 'wizard-behaviour.ts',
                  'wizard-behaviour.test.ts'):
            assert os.path.isfile(os.path.join(d, 'scripts', 'design', n)), n
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def new_files_name_no_other_project():
    bad = ('comic', 'twin', 'master', 'operator')
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


@test
def kit_self_tests_pass_under_node():
    if not node_ok():
        print('  (skipped: Node 22.6 or later not found)')
        return
    d = tempfile.mkdtemp()
    try:
        dest = os.path.join(d, 'scripts', 'design')
        shutil.copytree(KIT, dest)
        names = ['no-app-css.test.ts', 'dom-layout-judge.test.ts', 'wizard-behaviour.test.ts']
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
                           input=json.dumps(edit(d, 'web/a.tsx', '<button>')), capture_output=True, text=True)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out['hookSpecificOutput']['hookEventName'] == 'PostToolUse'
        r = subprocess.run([sys.executable, '-I', os.path.join(PLUGINS, 'delivery', 'scripts', 'hook_design_edit.py')],
                           input='not json', capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == ''  # never blocks, never crashes
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
def the_hook_is_a_draft_and_not_wired():
    hooks = open(os.path.join(PLUGINS, 'delivery', 'hooks', 'hooks.json'), encoding='utf-8').read()
    assert 'hook_design_edit' not in hooks


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
