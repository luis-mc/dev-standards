#!/usr/bin/env python3
"""Turn-start hook (UserPromptSubmit).

Stamps the start time of the turn for this session in <repo>/.claude/artifacts-stop-state.json, under the key
`turn:<session_id>` as {"start": <epoch seconds>}. The Stop hook (hook_end_of_turn.py) uses it to find the
reports written in this turn (owner decision D246). It writes nothing else, runs no git or gh command and never
blocks. Disable: CLAUDE_ARTIFACTS_HOOKS=off. Standard library only.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hook_after_command import (STATE_NAME, hook_root, hooks_off, read_input,  # noqa: E402
                                read_state, warn, write_state)


def main():
    if hooks_off():
        return 0
    data = read_input()
    root = hook_root(data)
    if not root or not os.path.isdir(os.path.join(root, '.claude')) and not os.path.isdir(os.path.join(root, 'docs')):
        return 0
    sid = str(data.get('session_id') or 'default')
    path = os.path.join(root, STATE_NAME)
    state = read_state(path)
    state.pop('turn:' + sid, None)     # keeps the most recently used session last
    state['turn:' + sid] = {'start': time.time()}
    write_state(path, state)
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # fail open: a broken hook must not trap the session
        warn('turn-start hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(0 if code is None else code)
