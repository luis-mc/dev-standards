#!/usr/bin/env python3
"""Run a declared test suite and record how long it took (STACKSPEC 13.8).

    run_suite.py --list
    run_suite.py NAME                 full run; records the time (local, this machine)
    run_suite.py NAME CASE [CASE ..]  named cases only; records nothing
    run_suite.py --measure NAME       full run to measure an unmeasured suite
    run_suite.py --record-ci NAME --seconds S [--tree TREE] [--failed]

Suites are declared in `scripts/delivery/suites.json` (or `.claude/suites.json`, or the
file named by $SUITES_JSON):

    {"schema": 1, "suites": [
      {"name": "unit", "full": "pnpm vitest run", "cases": "pnpm vitest run -t {cases}",
       "full_args": [], "ci_step": "unit", "measure": true}]}

`full` is the command of a full run; `cases` is the command for named cases, `{cases}`
standing for the quoted names; `full_args` lists flags that still make a command a full
run (default none: any other argument selects cases); `ci_step` names the CI job step
whose time ci_watch.py records; `"measure": false` marks a suite never run in full
locally (it stays heavy, and --measure is refused).

Times live in `.delivery/suite-times.json` (git-ignored with `.delivery/`), local runs
apart from CI runs. A suite is heavy when its last full local run took over
HEAVY_SECONDS, or has no local measurement. The session guard (session_guard.py) reads
the same file. Exit: the suite's own exit code; 2 usage or configuration error.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

HEAVY_SECONDS = 180
MEASURE_DAYS = 30
TIMES_PATH = ".delivery/suite-times.json"
SUITES_PATHS = ("scripts/delivery/suites.json", ".claude/suites.json")


class SuiteError(Exception):
    pass


def git(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return p.returncode, p.stdout.strip()


def repo_root(cwd: Path | str | None = None) -> Path:
    code, out = git(["rev-parse", "--show-toplevel"], Path(cwd or "."))
    return Path(out) if code == 0 and out else Path(cwd or ".").resolve()


def suites_file(root: Path) -> Path | None:
    env = os.environ.get("SUITES_JSON")
    if env:
        return Path(env) if Path(env).is_absolute() else root / env
    for rel in SUITES_PATHS:
        if (root / rel).is_file():
            return root / rel
    return None


def load_suites(root: Path) -> dict[str, dict]:
    """The declared suites by name; {} when the repository declares none."""
    path = suites_file(root)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SuiteError("%s is not valid JSON: %s" % (path, exc)) from None
    items = data.get("suites") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SuiteError("%s: expected {\"suites\": [...]}" % path)
    out: dict[str, dict] = {}
    for i, s in enumerate(items):
        if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not isinstance(s.get("full"), str):
            raise SuiteError("%s: suites[%d] needs a 'name' and a 'full' command" % (path, i))
        s.setdefault("cases", "")
        s.setdefault("full_args", [])
        s.setdefault("measure", True)
        out[s["name"]] = s
    return out


def tree_id(root: Path) -> str | None:
    """The tree a run tested: HEAD's tree when the checkout is clean, the index tree when
    only staged changes exist; None when unstaged or untracked files make it unknowable."""
    if git(["diff", "--quiet"], root)[0] != 0:
        return None
    if git(["ls-files", "--others", "--exclude-standard"], root)[1]:
        return None
    code, out = git(["write-tree"], root)
    return out if code == 0 and out else None


def read_times(root: Path) -> dict:
    try:
        data = json.loads((root / TIMES_PATH).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("local", {})
            data.setdefault("ci", {})
            return data
    except (OSError, ValueError):
        pass
    return {"local": {}, "ci": {}}


def write_times(root: Path, data: dict) -> None:
    path = root / TIMES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_days(record: dict) -> float | None:
    try:
        when = datetime.strptime(record["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return None
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400


def record(root: Path, kind: str, name: str, seconds: float, passed: bool, tree: str | None) -> None:
    data = read_times(root)
    data[kind][name] = {"seconds": round(seconds, 1), "at": now_iso(), "passed": passed,
                        "tree": tree, "machine": socket.gethostname()}
    write_times(root, data)


def local_record(times: dict, name: str) -> dict | None:
    rec = times.get("local", {}).get(name)
    if isinstance(rec, dict) and rec.get("machine") in (None, socket.gethostname()):
        return rec
    return None


def is_heavy(suite: dict, times: dict) -> bool:
    if not suite.get("measure", True):
        return True
    rec = local_record(times, suite["name"])
    return rec is None or not isinstance(rec.get("seconds"), (int, float)) or rec["seconds"] > HEAVY_SECONDS


def passed_on_tree(times: dict, name: str, tree: str | None) -> str | None:
    """'local' or 'CI' when a full run of the suite passed on this tree, else None."""
    if tree is None:
        return None
    for kind, label in (("local", "local"), ("ci", "CI")):
        rec = times.get(kind, {}).get(name)
        if isinstance(rec, dict) and rec.get("passed") and rec.get("tree") == tree:
            if kind == "local" and rec.get("machine") not in (None, socket.gethostname()):
                continue
            return label
    return None


def quote_args(cases: list[str]) -> str:
    """Quote for the shell subprocess uses: cmd.exe on Windows, sh elsewhere."""
    return subprocess.list2cmdline(cases) if os.name == "nt" else " ".join(shlex.quote(c) for c in cases)


def cases_command(suite: dict, cases: list[str]) -> str:
    template = suite.get("cases") or ""
    if "{cases}" not in template:
        raise SuiteError("suite '%s' does not declare how to run named cases" % suite["name"])
    return template.replace("{cases}", quote_args(cases))


def record_ci_times(root: Path, run: dict, jobs: list) -> None:
    """From a run's jobs (gh run view --json jobs): store the time of each suite's ci_step."""
    sha = str(run.get("headSha") or "")
    if not sha:
        return
    code, tree = git(["rev-parse", "--verify", "--quiet", sha + "^{tree}"], root)
    tree_val = tree if code == 0 and tree else None
    from datetime import datetime as _dt

    def parse(raw: object) -> float | None:
        if not isinstance(raw, str) or raw.startswith("0001"):
            return None
        try:
            return _dt.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    suites = load_suites(root)
    for suite in suites.values():
        step_name = suite.get("ci_step")
        if not step_name:
            continue
        for job in jobs:
            for step in (job.get("steps") or []) if isinstance(job, dict) else []:
                if not isinstance(step, dict) or str(step.get("name", "")).lower() != step_name.lower():
                    continue
                a, b = parse(step.get("startedAt")), parse(step.get("completedAt"))
                if a is None or b is None or b < a:
                    continue
                record(root, "ci", suite["name"], b - a, step.get("conclusion") == "success", tree_val)


def run_full(root: Path, suite: dict) -> int:
    tree = tree_id(root)
    print("run_suite: %s (full): %s" % (suite["name"], suite["full"]), flush=True)
    t0 = time.monotonic()
    code = subprocess.run(suite["full"], shell=True, cwd=root).returncode
    seconds = time.monotonic() - t0
    record(root, "local", suite["name"], seconds, code == 0, tree)
    print("run_suite: %s took %.1fs (%s); recorded in %s" % (
        suite["name"], seconds, "passed" if code == 0 else "failed", TIMES_PATH), flush=True)
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_suite.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("name", nargs="?", help="suite name")
    ap.add_argument("cases", nargs="*", help="case names; none means the full run")
    ap.add_argument("--list", action="store_true", help="list the suites, their times and weight")
    ap.add_argument("--measure", metavar="NAME", help="full run of an unmeasured suite, to record its time")
    ap.add_argument("--record-ci", metavar="NAME", help="store a CI time for the suite")
    ap.add_argument("--seconds", type=float, help="with --record-ci: the CI time")
    ap.add_argument("--tree", help="with --record-ci: the tree CI tested (default: HEAD's)")
    ap.add_argument("--failed", action="store_true", help="with --record-ci: the CI run failed")
    args = ap.parse_args(argv)
    root = repo_root()
    try:
        suites = load_suites(root)
        times = read_times(root)

        def need(name: str | None) -> dict:
            if not suites:
                raise SuiteError("no suites declared (scripts/delivery/suites.json)")
            if name not in suites:
                raise SuiteError("unknown suite %r; declared: %s" % (name, ", ".join(suites)))
            return suites[name]

        if args.list:
            for s in suites.values():
                rec = local_record(times, s["name"])
                ci = times.get("ci", {}).get(s["name"])
                print("%-24s %-6s local %s   ci %s" % (
                    s["name"], "heavy" if is_heavy(s, times) else "light",
                    "%.0fs" % rec["seconds"] if rec else "unmeasured",
                    "%.0fs" % ci["seconds"] if isinstance(ci, dict) else "-"))
            return 0
        if args.record_ci:
            suite = need(args.record_ci)
            if args.seconds is None:
                raise SuiteError("--record-ci needs --seconds")
            tree = args.tree or git(["rev-parse", "HEAD^{tree}"], root)[1] or None
            record(root, "ci", suite["name"], args.seconds, not args.failed, tree)
            return 0
        if args.measure:
            suite = need(args.measure)
            if not suite["measure"]:
                raise SuiteError("suite '%s' is declared with measure=false; it runs in CI only" % suite["name"])
            return run_full(root, suite)
        suite = need(args.name)
        if args.cases:
            cmd = cases_command(suite, args.cases)
            print("run_suite: %s (cases %s): %s" % (suite["name"], ", ".join(args.cases), cmd), flush=True)
            return subprocess.run(cmd, shell=True, cwd=root).returncode
        return run_full(root, suite)
    except SuiteError as exc:
        print("run_suite: error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
