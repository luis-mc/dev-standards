#!/usr/bin/env python3
"""DL-116 (DS261): the shared "changed areas" job. Which areas of the project does a change touch?

    changed_areas.py [--map .delivery/ci-areas.json] [--base REF | --changed-file FILE|- | PATH...]
                     [--release] [--all] [--github-output] [--json]
    changed_areas.py [--map FILE] unmapped [PATH...]     paths that fall to "all" (default: git ls-files)

The project owns `.delivery/ci-areas.json`:

    {
      "areas": {"code": ["src/**"], "web": ["apps/web/**"], "e2e": ["e2e/**"], "image": ["images/**"],
                "installer": ["installer/**"], "config": [".nvmrc", ".gitignore"]},
      "docs": ["docs/**", "**/*.md"],
      "all":  [".github/**", "package.json", ".delivery/**"],
      "release_full": true
    }

Rules, per changed path: a path under `all` runs everything; a `docs` path needs no job; a path in an area
selects that area (a path may sit in several); a path in none of them runs everything. An unknown path is never
skipped. No changed path is "all" too. On a release pull request (`--release`) the whole set runs unless
`release_full` is false (DL-97, DL-98 unchanged). `--all` forces everything (push to the default branch).

Output: `all=true|false`, `areas=a,b` (every area when all), `docs_only=true|false`, `<area>=true|false` for each
area, and `reason`. A job reads `needs.areas.outputs.<area>` in a job-level `if`; it never uses a workflow-level
paths filter (ci_areas_check.py). Built on area_select.py. Python 3.8+, standard library only.
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

DEFAULT_MAP = ".delivery/ci-areas.json"


def load_map(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("areas"), dict) or not data["areas"]:
        raise ValueError("%s: expected an object with a non-empty `areas` object" % path)
    for name, paths in data["areas"].items():
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise ValueError("%s: area %r needs a list of path patterns" % (path, name))
    for key in ("docs", "all"):
        if key in data and not (isinstance(data[key], list) and all(isinstance(p, str) for p in data[key])):
            raise ValueError("%s: `%s` must be a list of path patterns" % (path, key))
    return data


def _as_select_map(cmap: dict) -> dict:
    return {"areas": {n: {"paths": p} for n, p in cmap["areas"].items()},
            "run_everything": cmap.get("all") or [], "docs": cmap.get("docs") or []}


def classify(path: str, cmap: dict):
    """('all', why) | ('docs', '') | ('areas', [names]) for one path."""
    res = AS.select([path], _as_select_map(cmap))
    if res["mode"] == "all":
        return "all", res["reason"]
    if res["mode"] == "none":
        return "docs", ""
    return "areas", res["areas"]


def decide(changed, cmap: dict, release: bool = False, force_all: bool = False) -> dict:
    names = list(cmap["areas"])
    why = ""
    if force_all:
        why = "forced: run everything"
    elif release and cmap.get("release_full", True):
        force_all, why = True, "release pull request: run everything"
    res = AS.select(list(changed), _as_select_map(cmap), force_all)
    is_all = res["mode"] == "all"
    on = names if is_all else res["areas"]
    return {"all": is_all, "areas": on, "docs_only": res["mode"] == "none",
            "flags": {n: n in on for n in names}, "reason": why or res["reason"]}


def lines(res: dict) -> list:
    out = ["all=%s" % str(res["all"]).lower(), "areas=%s" % ",".join(res["areas"]),
           "docs_only=%s" % str(res["docs_only"]).lower()]
    out += ["%s=%s" % (n, str(on).lower()) for n, on in res["flags"].items()]
    out.append("reason=%s" % res["reason"])
    return out


def unmapped(paths, cmap: dict) -> list:
    """Paths that fall to "all" because no list names them (not the ones `all` names on purpose)."""
    sm = _as_select_map(cmap)
    out = []
    for p in paths:
        if AS.any_match(p, sm["run_everything"]) or AS.any_match(p, sm["docs"]):
            continue
        if not any(AS.any_match(p, a["paths"]) for a in sm["areas"].values()):
            out.append(p)
    return out


def git_files() -> list:
    r = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
    if r.returncode:
        raise OSError("git ls-files failed")
    return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="which areas does this change touch")
    p.add_argument("--map", default=DEFAULT_MAP)
    p.add_argument("--base")
    p.add_argument("--changed-file")
    p.add_argument("--release", action="store_true", help="a release pull request")
    p.add_argument("--all", action="store_true")
    p.add_argument("--github-output", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("paths", nargs="*")
    a = p.parse_args(argv)
    list_unmapped = bool(a.paths) and a.paths[0] == "unmapped"
    if list_unmapped:
        a.paths = a.paths[1:]
    try:
        cmap = load_map(a.map)
        changed = list(a.paths)
        if list_unmapped:
            for q in unmapped(changed or git_files(), cmap):
                print(q)
            return 0
        if a.changed_file:
            text = sys.stdin.read() if a.changed_file == "-" else Path(a.changed_file).read_text(encoding="utf-8")
            changed += text.splitlines()
        if a.base:
            changed += AS.changed_from_git(a.base)
    except (OSError, ValueError) as e:
        print("changed_areas: %s" % e, file=sys.stderr)
        return 2
    res = decide(changed, cmap, a.release, a.all)
    print(json.dumps(res, indent=1) if a.json else "\n".join(lines(res)))
    target = os.environ.get("GITHUB_OUTPUT")
    if a.github_output and target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines(res)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
