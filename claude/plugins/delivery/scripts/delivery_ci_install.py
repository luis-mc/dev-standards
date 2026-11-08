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

After the run (also with --dry-run) it checks the imports (DL112). For every .py it manages under
`scripts/delivery/` it reads the `import x` and `from x import y` lines (top level and inside functions) with
`ast`. A sibling module that is not in the project is listed under "missing imports:". In a git repo, managed
files that exist but are not tracked are listed under "not in git yet (commit them):". With --dry-run the
check looks at the project as it is now plus what the run would write.

Exit 0 done, 1 a bad track, 2 a missing template folder, 3 a managed script imports a sibling module that is
not in the project (the files were still written). Untracked files do not change the exit code.
Standard library only.
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
TEMPLATES = os.path.join(PLUGIN, "templates")
TRACKS = ("ts", "go", "rust", "dotnet")

# Project-edited: `update` never overwrites these (the project owns them after the first install).
PROJECT_OWNED_NAMES = {"gate.json", "smoke.json", "ci-areas.json", "ci-timings.json", "ci-scope.json",
                       "quarantine.json", "ci-shards.json", "ci-shards.example.json", "ci.yml", "package.yml", "nightly-full.yml"}
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


def imported_names(path: str) -> set:
    """Top-level module names a Python file imports (module level and inside functions)."""
    try:
        with open(path, "rb") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def missing_imports(items: list, root: str) -> list:
    """[(script, module)]: sibling modules a managed scripts/delivery/*.py imports that are not on disk in the project.

    A sibling is a module name that has a shipped file next to the script. With --dry-run nothing was written,
    so a file the run would write still counts as missing, but only when the importing script is already in the
    project (a dry run on an empty project has nothing to report).
    """
    shipped = {rel for rel, _s, _a in items}
    out = []
    for rel, src, _a in items:
        if not (rel.startswith("scripts/delivery/") and rel.endswith(".py")):
            continue
        if not os.path.exists(os.path.join(root, rel.replace("/", os.sep))):
            continue
        folder = rel.rsplit("/", 1)[0]
        for name in sorted(imported_names(src)):
            sibling = "%s/%s.py" % (folder, name)
            if sibling in shipped and not os.path.exists(os.path.join(root, sibling.replace("/", os.sep))):
                out.append((rel, name))
    return out


def untracked(items: list, root: str) -> list:
    """Managed files that exist in the project but are not tracked by git. [] when it is not a git repo."""
    try:
        proc = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    tracked = set(proc.stdout.decode("utf-8", "replace").split("\0"))
    return [rel for rel, _s, a in items if os.path.exists(os.path.join(root, rel.replace("/", os.sep)))
            and rel not in tracked]


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
    loose = untracked(items, root)
    if loose:
        print("not in git yet (commit them):")
        for rel in loose:
            print("  " + rel)
    missing = missing_imports(items, root)
    if missing:
        print("missing imports:")
        for rel, name in missing:
            print("  %s imports %s.py, which is not in %s" % (rel, name, rel.rsplit("/", 1)[0]))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
