#!/usr/bin/env python3
"""Before-command hook (PreToolUse for Bash and PowerShell).

ARTIFACTSPEC 1.3.1 section 8.6 (R8.16). Before `gh pr create`, `gh pr ready` or `gh pr merge`
runs, pushes the record commits that writing commands left unpushed
(`project_artifacts.py push`), so the pull request and the merge see the record the
work recorded. It never blocks the command: when the push fails or cannot run, it prints
a systemMessage saying so and exits 0. Every other command is passed through at once.

Seam for tests: CLAUDE_ARTIFACTS_SCRIPT overrides the path of project_artifacts.py.
Disable: CLAUDE_ARTIFACTS_HOOKS=off. Standard library only.
"""
import json
import os
import posixpath
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hook_after_command import (SEPARATORS, command_for, hook_root, hooks_off,  # noqa: E402
                                load_manifest, read_input, run, script_path, segment_tokens, warn)

PUSH_TIMEOUT = 60
PUSHED_COMMANDS = (('pr', 'create'), ('pr', 'ready'), ('pr', 'merge'))


def needs_record_push(command):
    """True when a segment of the command is gh pr create, ready or merge."""
    for seg in SEPARATORS.split(command):
        tokens = segment_tokens(seg)
        if len(tokens) >= 3 and posixpath.basename(tokens[0]).lower() in ('gh', 'gh.exe') \
                and tuple(tokens[1:3]) in PUSHED_COMMANDS:
            return True
    return False


def main():
    if hooks_off():
        return 0
    data = read_input()
    tool_input = data.get('tool_input')
    command = tool_input.get('command') if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not needs_record_push(command):
        return 0
    root = hook_root(data)
    if not root or load_manifest(root) is None:
        return 0
    r = run(command_for(script_path()) + ['push'], root, PUSH_TIMEOUT)
    if r is None:
        msg = 'the record push could not run; the record commits stay local'
    elif r[0] != 0:
        detail = (r[2] or r[1]).strip().splitlines()
        msg = 'the record push failed (exit %d%s); the record commits stay local and the end-of-turn hook ' \
              'tries again' % (r[0], ': ' + detail[-1][:200] if detail else '')
    else:
        return 0
    print(json.dumps({'systemMessage': 'luismc-artifacts: ' + msg}))
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # never block the command
        warn('before-command hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
