#!/usr/bin/env python3
"""Where the luismc-docs scripts are (DS296): one path locally and in the cloud.

Order: $DEV_STANDARDS_SCRIPTS when it names a folder with docs_check.py; the docs plugin next to this
one (marketplace checkout) or in the plugin cache (~/.claude/plugins/cache/*/luismc-docs/*/scripts, newest
version); else <project>/.dev-standards-tools/claude/plugins/docs/scripts. Prints the path (exit 1, no
output, when none exists). Standard library only.
"""
import glob
import os
import re
import sys

MARK = 'docs_check.py'
CHECKOUT = os.path.join('.dev-standards-tools', 'claude', 'plugins', 'docs', 'scripts')


def _ok(p):
    return bool(p) and os.path.isfile(os.path.join(p, MARK))


def _vkey(path):
    return [int(x) for x in re.findall(r'\d+', os.path.basename(os.path.dirname(path)))]


def resolve(project=None, home=None, plugin_root=None):
    env = os.environ.get('DEV_STANDARDS_SCRIPTS')
    if env and _ok(env):
        return os.path.abspath(env)
    here = plugin_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sibling = os.path.join(os.path.dirname(here), 'docs', 'scripts')
    if _ok(sibling):
        return sibling
    home = home or os.path.expanduser('~')
    cached = sorted(glob.glob(os.path.join(home, '.claude', 'plugins', 'cache', '*', 'luismc-docs', '*', 'scripts')),
                    key=_vkey, reverse=True)
    for c in cached:
        if _ok(c):
            return c
    local = os.path.join(os.path.abspath(project or os.getcwd()), CHECKOUT)
    return local if _ok(local) else None


if __name__ == '__main__':
    found = resolve(sys.argv[1] if len(sys.argv) > 1 else None)
    if found:
        print(found)
    sys.exit(0 if found else 1)
