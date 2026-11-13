#!/usr/bin/env python3
"""Adopt template changes into a project's installed CI files (DL308).

    template_adopt.py status [--root DIR]
    template_adopt.py diff PATH [--root DIR]
    template_adopt.py adopt PATH|--all [--dry-run] [--write-conflicts] [--root DIR]

Run from the project root. For each file the CI install manages there are three versions:
BASE (the template copy last installed, `.delivery/ci-install-base/<path>`), OURS (the project's file) and
THEIRS (the current plugin template). `status` prints one line per file: same, template-changed (ours == base),
project-changed (theirs == base), both-changed or missing. `diff` shows base -> theirs and base -> ours.
`adopt` merges with `git merge-file -p ours base theirs`. A clean merge is written and BASE becomes THEIRS.
A conflict changes nothing and exits 1; `--write-conflicts` writes the markers into the file instead.
With no stored base, `status` records the current template as the base and says so.
Never commits or pushes. Touches only files the install manages. Needs git on PATH. Standard library only.
"""
from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import delivery_ci_install as INS  # noqa: E402

SAME, TPL, PROJ, BOTH, MISSING = "same", "template-changed", "project-changed", "both-changed", "missing"


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read().replace(b"\r\n", b"\n")
    except OSError:
        return None


def installed(root):
    """{path: template file} for the files the install manages in this project."""
    tracks = INS.known_tracks(root)
    if not tracks:
        raise SystemExit("template_adopt: cannot tell the track; run delivery_ci_install.py update --track first")
    keep, skip = INS.load_config(root)
    skip = set(skip)
    if any(t in INS.WINDOWS_TRACKS for t in tracks) and INS.windows_deferred(root):
        skip |= set(INS.WINDOWS_FILES)
    if any(t in INS.PACKAGE_TRACKS for t in tracks) and not INS.has_packaged_program(root):
        skip |= set(INS.PACKAGE_FILES)
    src = INS.track_sources(tracks)
    return {r: s for r, s in sorted(src.items())
            if r not in skip and r not in INS.PROJECT_OWNED_PATHS and os.path.isfile(s)}


def versions(root, rel, src):
    """(base, ours, theirs) bytes with LF; each None when absent."""
    return (_read(INS.base_path(root, rel)), _read(os.path.join(root, rel.replace("/", os.sep))), _read(src))


def classify(base, ours, theirs):
    if ours is None:
        return MISSING
    if ours == theirs:
        return SAME
    if base is None:
        return PROJ
    if ours == base:
        return TPL
    if theirs == base:
        return PROJ
    return BOTH


def record_base(root, rel, data):
    bp = INS.base_path(root, rel)
    os.makedirs(os.path.dirname(bp), exist_ok=True)
    with open(bp, "wb") as f:
        f.write(data)


def three_way(base, ours, theirs):
    """(merged bytes, conflicts). Uses git merge-file."""
    with tempfile.TemporaryDirectory(prefix="adopt-") as d:
        paths = []
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            p = os.path.join(d, name)
            with open(p, "wb") as f:
                f.write(data)
            paths.append(p)
        try:
            r = subprocess.run(["git", "merge-file", "-p", "-L", "project", "-L", "base", "-L", "template"] + paths,
                               capture_output=True)
        except OSError:
            raise SystemExit("template_adopt: git is not on PATH")
        if r.returncode < 0 or r.returncode > 127:
            raise SystemExit("template_adopt: git merge-file failed: " + r.stderr.decode("utf-8", "replace").strip())
        return r.stdout, r.returncode


def cmd_status(root, items):
    for rel, src in items.items():
        base, ours, theirs = versions(root, rel, src)
        if base is None and theirs is not None and ours is not None:
            record_base(root, rel, theirs)
            print("%-17s %s (no base was stored; recorded the current template as the base)" % (classify(theirs, ours, theirs), rel))
            continue
        print("%-17s %s" % (classify(base, ours, theirs), rel))
    return 0


def _udiff(a, b, name_a, name_b):
    return "".join(difflib.unified_diff(a.decode("utf-8", "replace").splitlines(True), b.decode("utf-8", "replace").splitlines(True),
                                        name_a, name_b)) or "(no change)\n"


def cmd_diff(root, items, rel):
    if rel not in items:
        print("template_adopt: %s is not a file the install manages" % rel, file=sys.stderr)
        return 2
    base, ours, theirs = versions(root, rel, items[rel])
    if base is None:
        print("no base stored for %s; run status to record one" % rel, file=sys.stderr)
        return 1
    print("template change (base -> template):")
    print(_udiff(base, theirs, "base/" + rel, "template/" + rel), end="")
    print("project change (base -> project):")
    print(_udiff(base, ours or b"", "base/" + rel, "project/" + rel), end="")
    return 0


def adopt_one(root, rel, src, dry, write_conflicts):
    """Returns (outcome text, ok)."""
    base, ours, theirs = versions(root, rel, src)
    dst = os.path.join(root, rel.replace("/", os.sep))
    if base is None and ours is not None and theirs is not None and ours != theirs:
        if not dry:
            record_base(root, rel, theirs)
        return "no base stored: recorded the current template as the base, nothing merged; run status and adopt again", False
    kind = classify(base, ours, theirs)
    if kind == SAME:
        if base != theirs and not dry:
            record_base(root, rel, theirs)
        return "same", True
    if kind == PROJ:
        return "project-changed: nothing to adopt", True
    if kind == MISSING:
        if not dry:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(theirs)
            record_base(root, rel, theirs)
        return "missing: written from the template", True
    if kind == TPL:
        if not dry:
            with open(dst, "wb") as f:
                f.write(theirs)
            record_base(root, rel, theirs)
        return "copied the template", True
    merged, n = three_way(base, ours, theirs)
    if n == 0:
        if not dry:
            with open(dst, "wb") as f:
                f.write(merged)
            record_base(root, rel, theirs)
        return "merged", True
    if write_conflicts and not dry:
        with open(dst, "wb") as f:
            f.write(merged)
        return "conflict: %d hunk(s); markers written to the file, base unchanged" % n, False
    return "conflict: %d hunk(s); file unchanged (use --write-conflicts to write markers)\n%s" % (
        n, _udiff(ours, merged, "project/" + rel, "merged/" + rel)), False


def cmd_adopt(root, items, rel, all_, dry, write_conflicts):
    if all_:
        rest, code = [], 0
        for r, s in items.items():
            base, ours, theirs = versions(root, r, s)
            kind = classify(base, ours, theirs) if base is not None else None
            if kind not in (TPL, BOTH, MISSING):
                continue
            text, ok = adopt_one(root, r, s, dry, False)
            print("%-8s %s" % ("adopted" if ok else "left", r) + ("" if ok else ": " + text.splitlines()[0]))
            if not ok:
                rest.append(r)
        if rest:
            print("left for you: " + ", ".join(rest))
        return 1 if rest else 0
    if rel not in items:
        print("template_adopt: %s is not a file the install manages" % rel, file=sys.stderr)
        return 2
    text, ok = adopt_one(root, rel, items[rel], dry, write_conflicts)
    print(("[dry-run] " if dry else "") + rel + ": " + text)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="template_adopt.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["status", "diff", "adopt"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write-conflicts", action="store_true")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    rel = a.path.replace("\\", "/") if a.path else None
    if rel and rel.startswith("./"):
        rel = rel[2:]
    if a.action != "status" and not rel and not (a.action == "adopt" and a.all):
        ap.error("PATH is required")
    items = installed(root)
    if a.action == "status":
        return cmd_status(root, items)
    if a.action == "diff":
        return cmd_diff(root, items, rel)
    return cmd_adopt(root, items, rel, a.all, a.dry_run, a.write_conflicts)


if __name__ == "__main__":
    sys.exit(main())
