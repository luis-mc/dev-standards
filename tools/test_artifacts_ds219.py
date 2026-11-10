#!/usr/bin/env python3
"""DS219 (D182): where the project record lives when nothing says.

  1. no .claude/artifacts.json and no docs/docs.json record_dir: docs/project (unless only docs/artifacts holds a record)
  2. docs/docs.json record_dir, no artifacts.json: that folder
  3. .claude/artifacts.json without record_dir: docs/artifacts (the old default)
  4. .claude/artifacts.json record_dir wins over docs.json
  5. a broken artifacts.json falls back to docs/artifacts for the hooks, raises for the script
  6. the session hook (scripts/artifacts/) finds a record in docs/project

Run:  python -I tools/test_artifacts_ds219.py
Standard library only. Prints "N passed, M failed" and exits 0 when all pass.
"""
import json
import os
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), 'claude', 'plugins', 'docs', 'scripts')
sys.path.insert(0, SCRIPTS)
import artifact_queue as Q  # noqa: E402

TESTS = []


def case(fn):
    TESTS.append(fn)
    return fn


def write(root, rel, text):
    path = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


@case
def nothing_set_gives_docs_project():
    with tempfile.TemporaryDirectory() as d:
        assert Q.record_rel(d) == 'docs/project'
        write(d, 'docs/docs.json', json.dumps({'schema': 1}))
        assert Q.record_rel(d) == 'docs/project'
        assert Q.record_rel_safe(d) == 'docs/project'


@case
def a_record_already_in_docs_artifacts_is_still_found():
    with tempfile.TemporaryDirectory() as d:
        write(d, 'docs/artifacts/manifest.json', '{}')
        assert Q.record_rel(d) == 'docs/artifacts'
        write(d, 'docs/project/manifest.json', '{}')
        assert Q.record_rel(d) == 'docs/project'


@case
def docs_json_record_dir_is_used_without_artifacts_json():
    with tempfile.TemporaryDirectory() as d:
        write(d, 'docs/docs.json', json.dumps({'record_dir': 'docs/work/record'}))
        assert Q.record_rel(d) == 'docs/work/record'


@case
def artifacts_json_without_record_dir_keeps_docs_artifacts():
    with tempfile.TemporaryDirectory() as d:
        write(d, '.claude/artifacts.json', '{}')
        assert Q.record_rel(d) == 'docs/artifacts'


@case
def artifacts_json_record_dir_wins():
    with tempfile.TemporaryDirectory() as d:
        write(d, 'docs/docs.json', json.dumps({'record_dir': 'docs/project'}))
        write(d, '.claude/artifacts.json', json.dumps({'record_dir': 'docs/other'}))
        assert Q.record_rel(d) == 'docs/other'


@case
def broken_settings():
    with tempfile.TemporaryDirectory() as d:
        write(d, '.claude/artifacts.json', '{not json')
        assert Q.record_rel_safe(d) == 'docs/artifacts'
        try:
            Q.record_rel(d)
        except Q.RecordDirError:
            return
        raise AssertionError('record_rel accepted a broken artifacts.json')


@case
def session_hook_reads_a_record_in_docs_project():
    hook = os.path.join(SCRIPTS, 'artifacts', 'hook_session_start.py')
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(['git', 'init', '-q', d], check=True)
        write(d, 'docs/project/manifest.json', json.dumps({'schema': 1, 'artifacts': {}}))
        write(d, 'docs/project/registry.json', json.dumps({'schema': 1, 'tasks': []}))
        env = {k: v for k, v in os.environ.items() if not k.startswith('CLAUDE_ARTIFACTS_')}
        env['CLAUDE_ARTIFACTS_GH'] = os.path.join(d, 'missing-gh')
        p = subprocess.run([sys.executable, '-I', hook], cwd=d, input=json.dumps({'cwd': d}).encode(),
                           capture_output=True, env=env, timeout=60)
        assert p.returncode == 0, p.stderr
        out = p.stdout.decode('utf-8', 'replace')
        assert 'rules for work in this project' in out, out[:300]


def main():
    failed = 0
    for fn in TESTS:
        try:
            fn()
        except Exception:
            failed += 1
            traceback.print_exc()
            print('FAIL', fn.__name__)
    print('%d passed, %d failed' % (len(TESTS) - failed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
