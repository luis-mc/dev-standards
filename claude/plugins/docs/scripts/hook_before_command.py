#!/usr/bin/env python3
"""Before-command hook (retired; AR50, ARTIFACTSPEC 1.8.0).

Until 1.7.0 this hook pushed the record before `gh pr create`, `gh pr ready` and `gh pr merge`.
From 1.8.0 the plugin never commits or pushes: it writes the record files in docs/artifacts/ of
the working tree and stops, and the project commits them when it chooses. The hook therefore does
nothing: it prints nothing, runs no git or gh command and exits 0. It is no longer registered in
hooks/hooks.json; the file stays so an older hooks.json entry cannot fail.

Standard library only.
"""
import sys


def main():
    return 0


if __name__ == '__main__':
    sys.exit(main())
