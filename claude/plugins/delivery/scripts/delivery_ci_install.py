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

Keep and skip lists (DL120). A project may own `scripts/delivery/ci-install.json`. Install and update never
write or overwrite it. It has two lists of paths relative to the project root:

    {"keep": ["scripts/delivery/ci_watch.py"], "skip": [".github/workflows/package-windows.yml"]}

keep  `update` never overwrites these. When the template differs, the file is listed as
      "kept (ci-install.json)", and at the end one line per file says:
      "kept <path>: the plugin's version differs; diff it with <template path> and fold your change into the
      plugin or drop it". A kept file that is missing is still written.
skip  `install` and `update` never write these, even when missing. They are listed as "skipped (ci-install.json)".
A path in either list that the plugin does not manage prints a "warning:" line; it is not an error. A file that
is not valid JSON (or whose lists are not lists of strings) prints one line naming the file and exits 2. With
no ci-install.json the run is as before. The import check treats a skipped or kept file like any file on disk.
The plugin ships `ci-install.example.json` (empty lists and a `_comment`); it is copied like any template and
is never read as the real file.

Exit 0 done, 1 a bad track, 2 a missing template folder or a bad ci-install.json, 3 a managed script imports a sibling module that is
not in the project (the files were still written). Untracked files do not change the exit code.
Standard library only.
"""
from __future__ import annotations

import argparse
import ast
import json
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
                       "quarantine.json", "ci-shards.json", "ci-shards.example.json", "ci.yml", "package.yml", "nightly-full.yml",
                       "ci-install.json"}
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


CONFIG = "scripts/delivery/ci-install.json"
SKIPPED = "skipped (ci-install.json)"
KEPT = "kept (ci-install.json)"


def load_config(root: str):
    """(keep, skip) as sets of paths from the project's ci-install.json. ({}, {}) when absent. ValueError when bad."""
    path = os.path.join(root, CONFIG.replace("/", os.sep))
    if not os.path.exists(path):
        return set(), set()
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ValueError("%s is not valid JSON (%s)" % (CONFIG, e))
    if not isinstance(data, dict):
        raise ValueError("%s must be a JSON object with keep and skip lists" % CONFIG)
    lists = []
    for key in ("keep", "skip"):
        val = data.get(key, [])
        if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
            raise ValueError("%s: %r must be a list of paths" % (CONFIG, key))
        lists.append({(v.replace("\\", "/")[2:] if v.replace("\\", "/").startswith("./") else v.replace("\\", "/")) for v in val})
    return lists[0], lists[1]


def plan(track: str, root: str, mode: str, keep=(), skip=()) -> list:
    """[(relative path, source, action)] with action written | overwritten | kept | differs | same | skipped | kept (ci-install.json)."""
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
        if rel in skip and action in ("written", "overwritten"):
            action = SKIPPED
        elif rel in keep and action == "overwritten":
            action = KEPT
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
    try:
        keep, skip = load_config(root)
    except ValueError as e:
        print("delivery_ci_install: %s" % e, file=sys.stderr)
        return 2
    items = plan(args.track, root, args.action, keep, skip)
    managed = {rel for rel, _s, _a in items}
    for rel in sorted((keep | skip) - managed):
        print("warning: %s lists %s, which the plugin does not manage" % (CONFIG, rel))
    if not args.dry_run:
        apply(items, root)
    for rel, _src, action in items:
        if action != "same":
            print("%-11s %s" % (action, rel))
    counts = {}
    for _r, _s, a in items:
        counts[a] = counts.get(a, 0) + 1
    print("delivery_ci_install: %s" % ", ".join("%d %s" % (n, a) for a, n in sorted(counts.items())))
    for rel, src, action in items:
        if action == KEPT:
            print("kept %s: the plugin's version differs; diff it with %s and fold your change into the plugin or drop it"
                  % (rel, os.path.relpath(src, PLUGIN).replace(os.sep, "/")))
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
