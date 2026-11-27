#!/usr/bin/env python3
"""SessionStart hook (DS296): in a cloud session of a project with .delivery/ and
scripts/delivery/cloud_setup.sh, run the setup and name the docs scripts path. Does nothing
locally. Never blocks the session: a failure or a timeout prints a warning."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hooklib as H  # noqa: E402

TIMEOUT = int(os.environ.get('DELIVERY_CLOUD_SETUP_TIMEOUT', '150'))
DEFAULT = '.dev-standards-tools/claude/plugins/docs/scripts'


def main():
    if H.hooks_off() or os.environ.get('CLAUDE_CODE_REMOTE') != 'true':
        return 0
    root = H.find_root(H.read_input())
    script = os.path.join(root, 'scripts', 'delivery', 'cloud_setup.sh') if root else ''
    if not root or not os.path.isfile(script):
        return 0
    scripts = DEFAULT
    try:
        r = subprocess.run(['bash', script], cwd=root, capture_output=True, text=True, timeout=TIMEOUT)
        for line in r.stdout.splitlines():
            if line.startswith('DEV_STANDARDS_SCRIPTS='):
                scripts = line.split('=', 1)[1].strip() or DEFAULT
        if r.returncode != 0:
            H.warn('cloud_setup.sh exited %d: %s' % (r.returncode, (r.stderr or '').strip()[-300:]))
    except Exception as exc:     # includes the timeout; never block the session
        H.warn('cloud_setup.sh skipped (%s: %s)' % (type(exc).__name__, exc))
    ctx = ('luismc-delivery: cloud session. DEV_STANDARDS_SCRIPTS=%s (run docs_check.py and docs_fold.py from there; '
           'never hand-write change notes).' % scripts)
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': ctx}}))
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:     # fail open
        H.warn('cloud-setup hook skipped (%s: %s)' % (type(exc).__name__, exc))
        code = 0
    sys.exit(code or 0)
