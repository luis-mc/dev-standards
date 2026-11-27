#!/usr/bin/env python3
"""Decide which test areas and CI jobs a change needs (STACKSPEC 13.1, CI speed-ups).

    area_select.py [--map FILE] [--base REF | --changed-file FILE|- | PATH...] [--all]
                   [--github-output] [--json]

The changed paths come from `git diff --name-only --no-renames REF...HEAD` (`--base`), a list (`--changed-file`,
`-` is stdin) or the arguments. The project's committed map (default `scripts/delivery/ci-areas.json`):

    {
      "jobs":           ["verify", "integration", "e2e"],      every job the map can switch
      "always_jobs":    ["verify"],                            run whatever changed (static gates)
      "run_everything": ["package.json", "pnpm-lock.yaml", ".github/**", "scripts/delivery/**"],
      "docs":           ["docs/**", "**/*.md"],                changes here need no test
      "areas": {
        "api": {"paths": ["apps/api/**"], "jobs": ["integration"], "tests": ["apps/api/**/*.test.ts"]},
        "web": {"paths": ["apps/web/**"], "jobs": ["integration", "e2e"], "tests": ["apps/web/**/*.test.ts"]}
      }
    }

Globs: `**/` any directories (or none), `*` within one path segment, `?` one character; a plain
path with no glob character also matches everything under it. Per changed path, in this order:
  1. a `run_everything` match -> mode `all`;
  2. a `docs` match -> needs nothing;
  3. an `areas.*.paths` match -> that area (a path may belong to several; the areas are united);
  4. no match -> mode `all`. An unknown path is never skipped.
No changed path (an empty diff, no `--base`) is mode `all` too. Mode is `none` when every changed
path is documentation: only `always_jobs` run. `--all` forces mode `all` (a push to the default
branch, a manual run).

Output (stdout, JSON with `--json`, else `key=value` lines): `mode` (all|areas|none), `areas`
(comma-separated; `all` in mode all), `tests` (the test globs of the selected areas, space-separated,
empty in mode all because everything runs), one `<job>=true|false` per job, and `reason`.
`--github-output` appends the same lines to $GITHUB_OUTPUT. A job the map lists is true in mode all,
true when a selected area names it or it is in `always_jobs`, else false: a planned skip, which a
workflow must never count as a failure (a job gated on `== 'false'`, an aggregator that reads the plan).

Valves (R5.90, DS287), all optional; with none of these keys and no `workflow_path` the rules above are unchanged:
  `lock_jobs`    {"<glob>": ["job", ...]}: a changed lockfile or toolchain file runs only the listed jobs
                 (not everything). Checked before `run_everything`.
  `script_jobs`  true: a changed script under scripts/ci/** or scripts/delivery/** runs the jobs whose workflow text
                 names that script, plus the `ci_tests` area. It needs the workflow text (`workflow_text` of
                 select(), `--workflow FILE` on the CLI); without it the script falls to `run_everything`.
  workflow file  with `workflow_path` (`--workflow-path`): a change to that file runs every job (mode `all`); another
                 file under .github/workflows/ is no change for this workflow; .github/actions/** runs everything.

Exit: 0; 2 unreadable map, bad usage or `git` failure. Any doubt the script can see is mode `all`;
the workflow runs everything when the step itself fails (empty outputs).
Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shard_balance import glob_to_regex  # noqa: E402

DEFAULT_MAP = "scripts/delivery/ci-areas.json"
EXIT_USAGE = 2
GLOB_CHARS = re.compile(r"[*?]")


def matches(path: str, pattern: str) -> bool:
    pattern = pattern.replace("\\", "/")
    if GLOB_CHARS.search(pattern):
        return glob_to_regex(pattern).match(path) is not None
    pattern = pattern.rstrip("/")
    return path == pattern or path.startswith(pattern + "/")


def any_match(path: str, patterns: list[str]) -> bool:
    return any(matches(path, p) for p in patterns)


def load_map(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("areas"), dict):
        raise ValueError(f"{path}: expected an object with an `areas` object")
    for name, area in data["areas"].items():
        if not isinstance(area, dict) or not isinstance(area.get("paths"), list):
            raise ValueError(f"{path}: area {name!r} needs a `paths` list")
    return data


def all_jobs(cmap: dict) -> list[str]:
    jobs = list(cmap.get("jobs") or [])
    for area in cmap["areas"].values():
        jobs += [j for j in area.get("jobs") or [] if j not in jobs]
    jobs += [j for j in cmap.get("always_jobs") or [] if j not in jobs]
    return jobs


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse_workflow_jobs(text: str) -> dict[str, dict]:
    """{job key: {"name": display name or "", "text": the job's source}} read by indentation (no PyYAML)."""
    lines = text.splitlines()
    out: dict[str, dict] = {}
    start = next((i for i, ln in enumerate(lines) if re.match(r"^jobs:\s*(#.*)?$", ln)), None)
    if start is None:
        return out
    key_indent = None
    current = None
    for ln in lines[start + 1:]:
        if not ln.strip() or ln.lstrip().startswith("#"):
            if current:
                out[current]["text"] += ln + "\n"
            continue
        ind = _indent(ln)
        if ind == 0:
            break
        if key_indent is None:
            key_indent = ind
        m = re.match(r"^(['\"]?)([^\s:'\"#][^:'\"#]*)\1\s*:\s*(#.*)?$", ln.strip())
        if ind == key_indent and m:
            current = m.group(2).strip()
            out[current] = {"name": "", "text": ln + "\n"}
            continue
        if current:
            out[current]["text"] += ln + "\n"
            nm = re.match(r"^name:\s*(.*?)\s*$", ln.strip())
            if nm and not out[current]["name"] and ind <= key_indent + 4:
                val = re.sub(r"\s+#.*$", "", nm.group(1)).strip()
                out[current]["name"] = val[1:-1] if len(val) > 1 and val[0] == val[-1] and val[0] in "'\"" else val
    return out


def jobs_naming_script(workflow_text: str, script: str) -> list[str]:
    """Job keys whose workflow text names `script` (its path or its file name)."""
    base = script.rsplit("/", 1)[-1]
    pat = re.compile(r"(?<![\w.\-])(?:" + re.escape(script) + "|" + re.escape(base) + r")(?![\w])")
    return [k for k, j in parse_workflow_jobs(workflow_text).items() if pat.search(j["text"])]


SCRIPT_DIRS = ["scripts/ci/**", "scripts/delivery/**"]


def select(changed: list[str], cmap: dict, force_all: bool = False, workflow_text: str | None = None,
           workflow_path: str | None = None) -> dict:
    jobs = all_jobs(cmap)
    always = set(cmap.get("always_jobs") or [])
    paths = [re.sub(r"^\./", "", c.strip().replace("\\", "/")) for c in changed if c.strip()]

    extra: set[str] = set()

    def result(mode: str, areas: list[str], reason: str) -> dict:
        if mode == "all":
            on = set(jobs)
            tests: list[str] = []
        else:
            on = set(always) | extra
            tests = []
            for a in areas:
                on |= set(cmap["areas"][a].get("jobs") or [])
                tests += [t for t in cmap["areas"][a].get("tests") or [] if t not in tests]
        return {
            "mode": mode,
            "areas": ["all"] if mode == "all" else areas,
            "tests": tests,
            "jobs": {j: j in on for j in jobs},
            "reason": reason,
        }

    if force_all:
        return result("all", [], "forced: run everything")
    if not paths:
        return result("all", [], "no changed paths: run everything")
    areas: list[str] = []
    wf_dir = ".github/workflows/"
    lock_jobs = cmap.get("lock_jobs") if isinstance(cmap.get("lock_jobs"), dict) else {}
    for p in paths:
        if workflow_path:
            if p == re.sub(r"^\./", "", workflow_path):
                return result("all", [], f"{p} is this workflow: run all its jobs")
            if p.startswith(wf_dir) and any_match(p, ["**/*.yml", "**/*.yaml"]):
                continue  # another workflow file: no change for this one
            if matches(p, ".github/actions"):
                return result("all", [], f"{p} is a shared action: run everything")
        locked = [j for g, js in lock_jobs.items() if matches(p, g) for j in js or []]
        if locked:
            extra.update(locked)
            continue
        if cmap.get("script_jobs") is True and workflow_text is not None and any_match(p, SCRIPT_DIRS):
            named = jobs_naming_script(workflow_text, p)
            if "ci_tests" in cmap["areas"] or named:
                extra.update(named)
                if "ci_tests" in cmap["areas"] and "ci_tests" not in areas:
                    areas.append("ci_tests")
                continue
        if any_match(p, cmap.get("run_everything") or []):
            return result("all", [], f"{p} is shared: run everything")
        if any_match(p, cmap.get("docs") or []):
            continue
        hit = [n for n, a in cmap["areas"].items() if any_match(p, a["paths"])]
        if not hit:
            return result("all", [], f"{p} is in no area: run everything")
        areas += [n for n in hit if n not in areas]
    if not areas and extra:
        return result("areas", [], "valves: " + ", ".join(sorted(extra)))
    if not areas:
        return result("none", [], "documentation only: no tests")
    return result("areas", sorted(areas), "areas: " + ", ".join(sorted(areas)))


def changed_from_git(base: str) -> list[str]:
    # --no-renames: a moved file counts at its old and its new path. -z: real names, no quoting.
    flags = ["git", "diff", "--name-only", "--no-renames", "-z"]
    out = subprocess.run([*flags, f"{base}...HEAD"], capture_output=True)
    if out.returncode != 0:
        out = subprocess.run([*flags, base, "HEAD"], capture_output=True)
    if out.returncode != 0:
        raise OSError(f"git diff {base} failed: {out.stderr.decode('utf-8', 'replace').strip()}")
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p.strip()]


def lines(res: dict) -> list[str]:
    out = [f"mode={res['mode']}", f"areas={','.join(res['areas'])}", f"tests={' '.join(res['tests'])}"]
    out += [f"{j}={'true' if on else 'false'}" for j, on in res["jobs"].items()]
    out.append(f"reason={res['reason']}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="which test areas and CI jobs does this change need")
    p.add_argument("--map", default=DEFAULT_MAP)
    p.add_argument("--base")
    p.add_argument("--changed-file")
    p.add_argument("--workflow", help="the workflow file's text, for script_jobs")
    p.add_argument("--workflow-path", help="the path of the current workflow file, e.g. .github/workflows/ci.yml")
    p.add_argument("--all", action="store_true", help="run everything (push to the default branch, manual run)")
    p.add_argument("--github-output", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("paths", nargs="*")
    args = p.parse_args(argv)
    try:
        cmap = load_map(Path(args.map))
        changed = list(args.paths)
        if args.changed_file:
            text = sys.stdin.read() if args.changed_file == "-" else Path(args.changed_file).read_text(encoding="utf-8")
            changed += text.splitlines()
        if args.base:
            changed += changed_from_git(args.base)
    except (OSError, ValueError) as e:
        print(f"area_select: {e}", file=sys.stderr)
        return EXIT_USAGE
    wtext = None
    if args.workflow:
        try:
            wtext = Path(args.workflow).read_text(encoding="utf-8")
        except OSError as e:
            print(f"area_select: {e}", file=sys.stderr)
            return EXIT_USAGE
    res = select(changed, cmap, args.all, wtext, args.workflow_path)
    print(json.dumps(res, indent=1) if args.json else "\n".join(lines(res)))
    target = os.environ.get("GITHUB_OUTPUT")
    if args.github_output and target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines(res)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
