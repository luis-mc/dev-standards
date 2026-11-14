#!/usr/bin/env python3
"""DL334: the PR exception of DL-73 in the rules asset and the claude-setup settings."""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
ASSETS = os.path.join(ROOT, 'claude/plugins/project-setup/skills/claude-setup')
RULES = os.path.join(ASSETS, 'assets/.claude/rules/agents-and-integration.md')
SETTINGS = os.path.join(ASSETS, 'assets/.claude/settings.json')
SKILL = os.path.join(ASSETS, 'SKILL.md')
WANT = ['Bash(gh pr create:*)', 'Bash(gh pr ready:*)', 'Bash(gh pr edit:*)']


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def test_rules_carry_exception_and_tag():
    line = [l for l in read(RULES).splitlines() if 'check: DL-73' in l]
    assert len(line) == 1
    assert 'open pull requests' in line[0] and 'merging stays the owner' in line[0]
    assert 'comments or reviews' in line[0]


def test_settings_allow_three_pr_rules_not_merge():
    allow = json.loads(read(SETTINGS))['permissions']['allow']
    for w in WANT:
        assert allow.count(w) == 1
    assert not any('merge' in a for a in allow)


def test_skill_describes_the_step():
    s = read(SKILL)
    for w in WANT:
        assert w in s
    assert 'gh pr merge' in s and 'DL-73' in s
    assert 'Bash(gh pr merge' not in s


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
    sys.exit(0)
