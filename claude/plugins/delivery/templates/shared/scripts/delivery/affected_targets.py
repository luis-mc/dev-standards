#!/usr/bin/env python3
"""DL-125 (DS269): which lifecycle targets does a change affect? A pull request proves only those.

    affected_targets.py [--lifecycle lifecycle.json] [--base REF | --changed-file FILE|- | PATH...] [--all]
                        [--github-output] [--json]
    affected_targets.py lane --lane L [same options]     run=true|false for one lifecycle lane
    affected_targets.py unmapped [PATH...]               tracked paths that map to no target and are not `no_target`
    affected_targets.py scaffold [--lifecycle F] [--write]   add `inputs` and `no_target` to an older lifecycle.json

`lifecycle.json` gives each target `inputs` (path globs) and may give a top-level `no_target` list (docs and
the like: paths that affect no target). Per changed path:
  - under a shared path: every target. Shared: lifecycle.json, the lane scripts and workflow, pass_records.py,
    affected_targets.py, and files directly in packaging/ or installer/;
  - matching a target's `inputs`: that target (a path may match several);
  - matching `no_target`: none;
  - matching nothing: every target. An unknown path is never skipped.
A target with no `inputs` is always affected. No changed path, a diff that cannot be read, or `--all` means every
target. Output: `all=true|false`, `targets=lane/arch/package,...`, `reason=...`; with `lane`, also `run=true|false`.
A lane that is not affected may take its result from a pass record of the default branch (pass_records.py
to-result); a miss runs the lane. Python 3.8+, standard library only. Exit 0 ok, 2 bad input.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import area_select as AS  # noqa: E402

SHARED = ["**/lifecycle.json", "lifecycle.json", "scripts/lifecycle/**", "templates/lifecycle/**",
          "scripts/delivery/lifecycle_*.py", "scripts/delivery/pass_records.py", "scripts/delivery/affected_targets.py",
          ".github/workflows/lifecycle*.yml", ".github/workflows/lifecycle*.yaml",
          "packaging/*", "installer/*"]
DEFAULT_NO_TARGET = ["docs/**", "**/*.md"]
DEFAULT_INPUTS = {   # `scaffold` only: a start for the project to review
    "windows": ["installer/windows/**", "packaging/windows/**"],
    "linux": ["installer/linux/**", "packaging/linux/**"],
    "macos": ["installer/macos/**", "packaging/macos/**"],
}


def lane_of(t: dict) -> str:
    return t.get("distro") or t["os"]


def name_of(t: dict) -> str:
    return "%s/%s/%s" % (lane_of(t), t.get("arch"), t.get("package"))


def _globs(value) -> list:
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def classify(path: str, lc: dict):
    """('all', why) | ('none', '') | ('targets', [indexes]) for one changed path."""
    path = path.replace("\\", "/")
    if AS.any_match(path, SHARED):
        return "all", "shared path %s" % path
    hit = [i for i, t in enumerate(lc.get("targets") or [])
           if AS.any_match(path, _globs(t.get("inputs")))]
    if hit:
        return "targets", hit
    if AS.any_match(path, _globs(lc.get("no_target"))):
        return "none", ""
    return "all", "unknown path %s" % path


def decide(changed, lc: dict, force_all: bool = False) -> dict:
    targets = lc.get("targets") or []
    every = list(range(len(targets)))
    why = "forced: every target" if force_all else ""
    on = set()
    if not force_all and not list(changed):
        force_all, why = True, "no changed path: every target"
    if not force_all:
        for p in changed:
            kind, val = classify(p, lc)
            if kind == "all":
                force_all, why = True, val
                break
            if kind == "targets":
                on.update(val)
    on.update(i for i, t in enumerate(targets) if not _globs(t.get("inputs")))   # no inputs: always affected
    chosen = every if force_all else sorted(on)
    return {"all": force_all, "targets": [name_of(targets[i]) for i in chosen],
            "lanes": sorted({lane_of(targets[i]) for i in chosen}),
            "reason": why or ("%d of %d targets" % (len(chosen), len(targets)))}


def lines(res: dict, lane=None) -> list:
    out = ["all=%s" % str(res["all"]).lower(), "targets=%s" % ",".join(res["targets"]), "reason=%s" % res["reason"]]
    if lane:
        out.append("run=%s" % str(lane in res["lanes"]).lower())
    return out


def unmapped(paths, lc: dict) -> list:
    """Paths that fall to 'every target' because nothing names them (not the shared paths, which do so on purpose)."""
    out = []
    for p in paths:
        kind, why = classify(p, lc)
        if kind == "all" and why.startswith("unknown"):
            out.append(p)
    return out


def scaffold(lc: dict) -> dict:
    """A copy of lifecycle.json with `inputs` on each target that has none and `no_target` when missing."""
    out = json.loads(json.dumps(lc))
    for t in out.get("targets") or []:
        if not _globs(t.get("inputs")):
            t["inputs"] = list(DEFAULT_INPUTS.get(t.get("os"), []))
    out.setdefault("no_target", list(DEFAULT_NO_TARGET))
    return out


def project_files(root=".") -> list:
    """Tracked paths of the project at root, or [] when it is not a git work tree."""
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    except OSError:
        return []
    return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p] if r.returncode == 0 else []


def find_lifecycle(root=".", files=None):
    """The tracked lifecycle.json of the project (the shortest path), or None."""
    files = project_files(root) if files is None else files
    found = sorted((p for p in files if p == "lifecycle.json" or p.endswith("/lifecycle.json")), key=lambda p: (len(p), p))
    return str(Path(root) / found[0]) if found else None


def status(root="."):
    """(lifecycle path, targets, unmapped paths) for the project, or None when it has no lifecycle.json (DL-125)."""
    files = project_files(root)
    path = find_lifecycle(root, files)
    if not path:
        return None
    lc = json.loads(Path(path).read_text(encoding="utf-8"))
    return path, len(lc.get("targets") or []), unmapped(files, lc)


def hook_line(root="."):
    """One line for the session start while the project has a lifecycle.json; empty otherwise or on any error."""
    try:
        st = status(root)
    except (OSError, ValueError):
        return ""
    if not st:
        return ""
    n = len(st[2])
    return ("Lifecycle: a pull request proves only the targets its changes affect (DL-125, %d targets); %d tracked path%s map%s "
            "to no target and run every target." % (st[1], n, "" if n == 1 else "s", "s" if n == 1 else ""))


def git_files() -> list:
    r = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
    if r.returncode:
        raise OSError("git ls-files failed")
    return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="which lifecycle targets does this change affect")
    ap.add_argument("--lifecycle", default=os.environ.get("LIFECYCLE_JSON", "docs/design-system/lifecycle.json"))
    ap.add_argument("--base")
    ap.add_argument("--changed-file")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--lane")
    ap.add_argument("--write", action="store_true", help="scaffold: write the file instead of printing it")
    ap.add_argument("--github-output", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("paths", nargs="*")
    a = ap.parse_intermixed_args(argv)
    mode = "affected"
    if a.paths and a.paths[0] in ("lane", "unmapped", "scaffold"):
        mode, a.paths = a.paths[0], a.paths[1:]
    try:
        lc = json.loads(Path(a.lifecycle).read_text(encoding="utf-8"))
        if not isinstance(lc, dict) or not isinstance(lc.get("targets") or [], list):
            raise ValueError("%s: expected an object with a `targets` list" % a.lifecycle)
    except (OSError, ValueError) as e:
        print("affected_targets: %s" % e, file=sys.stderr)
        return 2
    if mode == "scaffold":
        new = scaffold(lc)
        text = json.dumps(new, indent=2) + "\n"
        if a.write:
            Path(a.lifecycle).write_text(text, encoding="utf-8")
            print("wrote %s: review `inputs` and `no_target`; a path that maps to nothing runs every target" % a.lifecycle)
        else:
            print(text, end="")
        return 0
    if mode == "unmapped":
        try:
            for q in unmapped(a.paths or git_files(), lc):
                print(q)
        except OSError as e:
            print("affected_targets: %s" % e, file=sys.stderr)
            return 2
        return 0
    if mode == "lane" and not a.lane:
        print("affected_targets: lane needs --lane", file=sys.stderr)
        return 2
    changed, failed = list(a.paths), ""
    try:
        if a.changed_file:
            text = sys.stdin.read() if a.changed_file == "-" else Path(a.changed_file).read_text(encoding="utf-8")
            changed += [x for x in text.splitlines() if x.strip()]
        if a.base:
            changed += AS.changed_from_git(a.base)
    except OSError as e:
        failed = "cannot read the change (%s): every target" % e
    res = decide(changed, lc, a.all or bool(failed))
    if failed:
        res["reason"] = failed
    out = lines(res, a.lane if mode == "lane" else None)
    print(json.dumps(res, indent=1) if a.json else "\n".join(out))
    target = os.environ.get("GITHUB_OUTPUT")
    if a.github_output and target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
