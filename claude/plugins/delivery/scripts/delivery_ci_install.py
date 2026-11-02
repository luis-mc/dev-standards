#!/usr/bin/env python3
"""Write the CI and delivery files into a project, or update them (DL15).

    delivery_ci_install.py install --track ts|go|rust|dotnet [--root DIR] [--dry-run]
    delivery_ci_install.py update  --track ts|go|rust|dotnet [--root DIR] [--dry-run]

The sources are `templates/shared/` and `templates/<track>/` next to this plugin. They land at the same
relative path in the project (`scripts/delivery/`, `.github/workflows/`). tech-stack-setup calls `install` at
the end of its setup; it copies none of these files itself.

install  writes every file that is not there yet. A file that exists and differs is kept and listed as
         "kept"; nothing is overwritten.
update   overwrites the files the plugin owns (scripts, CONTRACT.md, tools.json, shared workflows) and keeps
         the files the project edits (the *.json maps, gate.json, smoke.json, quarantine, ci.yml, package.yml,
         nightly-full.yml). A kept file that differs is listed as "differs".

It never commits or pushes, and it does not choose the CI option: ask the owner, then run
`delivery_ci.py set`. The GitHub workflow files are always written; a project that runs an OS only in cloud
sessions (option c) deletes the jobs it does not use. `CONTRACT.md` is not installed: it stays with the plugin.
Exit 0 done, 1 a bad track, 2 a missing template folder. Standard library only.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
TEMPLATES = os.path.join(PLUGIN, "templates")
TRACKS = ("ts", "go", "rust", "dotnet")

# Project-edited: `update` never overwrites these (the project owns them after the first install).
PROJECT_OWNED_NAMES = {"gate.json", "smoke.json", "ci-areas.json", "ci-timings.json", "ci-scope.json",
                       "quarantine.json", "ci-shards.json", "ci.yml", "package.yml", "nightly-full.yml"}
SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {"CONTRACT.md"}


def files_of(base: str) -> list:
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(f for f in filenames if f not in SKIP_FILES):
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, base).replace(os.sep, "/"))
    return out


def same(a: str, b: str) -> bool:
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read().replace(b"\r\n", b"\n") == fb.read().replace(b"\r\n", b"\n")


def plan(track: str, root: str, mode: str) -> list:
    """[(relative path, source, action)] with action written | overwritten | kept | differs | same."""
    out, sources = [], {}
    for part in ("shared", track):
        base = os.path.join(TEMPLATES, part)
        for rel in files_of(base):
            sources[rel] = os.path.join(base, rel.replace("/", os.sep))
    for rel in sorted(sources):
        src, dst = sources[rel], os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(dst):
            action = "written"
        elif same(src, dst):
            action = "same"
        elif mode == "update" and os.path.basename(rel) not in PROJECT_OWNED_NAMES:
            action = "overwritten"
        else:
            action = "differs" if mode == "update" else "kept"
        out.append((rel, src, action))
    return out


def apply(items: list, root: str) -> None:
    for rel, src, action in items:
        if action not in ("written", "overwritten"):
            continue
        dst = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        if rel.endswith(".sh") or rel.endswith(".py"):
            try:
                os.chmod(dst, os.stat(dst).st_mode | 0o111)
            except OSError:
                pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_ci_install.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["install", "update"])
    ap.add_argument("--track", required=True)
    ap.add_argument("--root", default=".", help="the project root (default: the current folder)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.track not in TRACKS:
        print("delivery_ci_install: --track must be one of %s" % ", ".join(TRACKS), file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join(TEMPLATES, "shared")) or not os.path.isdir(os.path.join(TEMPLATES, args.track)):
        print("delivery_ci_install: no templates for %r under %s" % (args.track, TEMPLATES), file=sys.stderr)
        return 2
    root = os.path.abspath(args.root)
    items = plan(args.track, root, args.action)
    if not args.dry_run:
        apply(items, root)
    for rel, _src, action in items:
        if action != "same":
            print("%-11s %s" % (action, rel))
    counts = {}
    for _r, _s, a in items:
        counts[a] = counts.get(a, 0) + 1
    print("delivery_ci_install: %s" % ", ".join("%d %s" % (n, a) for a, n in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
