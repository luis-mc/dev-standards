#!/usr/bin/env python3
"""Prints exactly what a session's hourly cron should do for Full Progress, or nothing (R9.10).

    publish_hourly.py [--root DIR]

Silent (exit 0) when Full Progress was published within the last 60 minutes and no release task
changed since. Otherwise prints the three commands that publish it, naming the URL to update.
It only reads the record and never publishes itself: the Artifact tool is the session's.
Standard library only.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import artifact_hourly as H  # noqa: E402


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def reasons(manifest, tasks, now=None):
    """Why Full Progress should be published now; [] when nothing is due."""
    out = []
    if H.published_at(manifest) is None:
        return ['Full Progress has not been published yet']
    mins = H.hourly_due(manifest, now)
    if mins is not None:
        out.append('Full Progress was last published %d minutes ago (hourly fail-safe, limit %d)' % (mins, H.STALE_MINUTES))
    for t in H.release_changes(tasks, manifest):
        out.append('release task %s changed (%s) after the last publish' % (t.get('id'), t.get('status')))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', help='repository root (default: the repository of the current directory)')
    args = ap.parse_args(argv)
    if args.root:
        root = args.root
    else:
        from artifact_queue import repo_root
        root = repo_root(None)
    if not root:
        return 0
    rec = os.path.join(root, 'docs', 'artifacts')
    manifest = read_json(os.path.join(rec, 'manifest.json'))
    if manifest is None:
        return 0
    registry = read_json(os.path.join(rec, 'registry.json')) or {}
    tasks = [t for t in registry.get('tasks', []) if isinstance(t, dict)] if isinstance(registry.get('tasks'), list) else []
    why = reasons(manifest, tasks)
    if not why:
        return 0
    script = os.environ.get('CLAUDE_ARTIFACTS_SCRIPT') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'project_artifacts.py')
    py = 'python "%s"' % script
    url = H.full_progress(manifest).get('url') or ''
    print('Publish Full Progress now: ' + '; '.join(why) + '.')
    print('1. Run: %s pending --json --refresh   (writes the publish copy and prints its path)' % py)
    print('2. Publish that copy with the Artifact tool, unedited%s.'
          % ((', updating the existing artifact at ' + url) if url else ' (first publish)'))
    print('3. Run: %s mark-published full-progress --url <the artifact URL>' % py)
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception as exc:   # a cron helper never fails loudly
        print('luismc-artifacts: publish_hourly skipped (%s: %s)' % (type(exc).__name__, exc), file=sys.stderr)
        code = 0
    sys.exit(code)
