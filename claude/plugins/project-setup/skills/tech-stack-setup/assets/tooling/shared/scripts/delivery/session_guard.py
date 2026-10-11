#!/usr/bin/env python3
"""Claude Code PreToolUse hook for Bash commands (STACKSPEC 13.8).

Reads the hook JSON on stdin ({"tool_input": {"command": ...}, "cwd": ...}). Exit 0
allows the command; exit 2 refuses it with the reason on stderr (Claude Code's blocking
convention). Two guards:

  Test guard. Refuses a full local run of a heavy suite, a full local run of a suite
  whose last full run (local or CI) passed on the same tree, and `run_suite.py --measure`
  when a measurement under 30 days old exists. A suite is recognised by the commands in
  suites.json, typed directly or through run_suite.py. Named-case runs are always allowed.
  Heavy: last full local run over 180 s, no local measurement, or "measure": false.

  Ready-PR guard. Refuses `gh pr create` without --draft, and `gh pr ready`, when the head
  branch (the current branch, or --head) is not a release branch: `release_branches`
  of tools/change-notes.json, default `*-integration`.

A command it cannot parse, or a repository without suites, is allowed. An internal error
prints a warning and exits 1 (non-blocking). Also usable by hand:
`session_guard.py --check "COMMAND"`.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_suite as rs  # noqa: E402

DEFAULT_RELEASE_BRANCHES = ["*-integration"]
REDIRECT = re.compile(r"^\d*>{1,2}(&\d+|\S*)$")
SPLIT = re.compile(r"&&|\|\||[;|\n]")
INTERPRETERS = {"python3": "python", "py": "python", "python3.11": "python", "python3.12": "python"}


def tokens(segment: str) -> list[str]:
    if os.name == "nt":
        segment = segment.replace("\\", "/")  # Windows paths; shlex would read them as escapes
    try:
        toks = shlex.split(segment)
    except ValueError:
        toks = segment.split()
    toks = [t for t in toks if not REDIRECT.match(t)]
    # leading noise: VAR=x, rtk, timeout N, env
    while toks:
        t = toks[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) or t in ("rtk", "env", "command", "exec"):
            toks = toks[1:]
        elif t == "timeout" and len(toks) > 2:
            toks = toks[2:]
        else:
            break
    if toks:
        toks[0] = INTERPRETERS.get(toks[0], toks[0])
        toks = [t[2:] if t.startswith("./") else t for t in toks]
    return toks


def segments(command: str) -> list[list[str]]:
    return [t for t in (tokens(s) for s in SPLIT.split(command)) if t]


def full_run_of(suite: dict, toks: list[str]) -> bool:
    """True when toks is the suite's full command, plus only its declared full_args."""
    full = tokens(suite["full"])
    if not full or toks[: len(full)] != full:
        return False
    return all(t in suite.get("full_args", []) for t in toks[len(full):])


def check_tests(root: Path, toks: list[str]) -> str | None:
    try:
        suites = rs.load_suites(root)
    except rs.SuiteError:
        return None
    if not suites:
        return None
    times = rs.read_times(root)
    tree = None
    script = next((i for i, t in enumerate(toks) if os.path.basename(t) == "run_suite.py"), None)
    if script is not None:
        args = toks[script + 1:]
        if "--list" in args or "--record-ci" in args:
            return None
        if "--measure" in args:
            i = args.index("--measure")
            name = args[i + 1] if i + 1 < len(args) else ""
            suite = suites.get(name)
            if suite is None:
                return None
            if not suite.get("measure", True):
                return ("%s is declared measure=false: it is never run in full locally. Run named cases "
                        "(run_suite.py %s CASE ...) and leave the full run to CI." % (name, name))
            rec = rs.local_record(times, name)
            age = rs.age_days(rec) if rec else None
            if age is not None and age < rs.MEASURE_DAYS:
                return ("%s was measured %.0f days ago (%.0fs); a measurement under %d days is kept. "
                        "Run named cases (run_suite.py %s CASE ...) or leave the full run to CI."
                        % (name, age, rec["seconds"], rs.MEASURE_DAYS, name))
            return None
        positional = [a for a in args if not a.startswith("-")]
        if len(positional) != 1 or positional[0] not in suites:
            return None  # named cases, or not a suite
        suite = suites[positional[0]]
    else:
        suite = next((s for s in suites.values() if full_run_of(s, toks)), None)
        if suite is None:
            return None
    name = suite["name"]
    cases_hint = ("run named cases of the part you touched (run_suite.py %s CASE ...%s) and leave "
                  "the full run to CI (gh workflow run <workflow> --ref <branch>, watched with "
                  "scripts/delivery/ci_watch.py)" % (name, ""))
    if rs.is_heavy(suite, times):
        rec = rs.local_record(times, name)
        why = ("is declared measure=false" if not suite.get("measure", True)
               else "has no local measurement yet" if rec is None
               else "took %.0fs on its last full local run (over %ds)" % (rec["seconds"], rs.HEAVY_SECONDS))
        extra = ""
        if suite.get("measure", True) and rec is None:
            extra = " To measure it once: run_suite.py --measure %s." % name
        return "%s is a heavy suite: it %s. Do not run it in full locally; %s.%s" % (name, why, cases_hint, extra)
    tree = rs.tree_id(root)
    where = rs.passed_on_tree(times, name, tree)
    if where:
        return ("%s already passed a full run (%s) on this exact tree. Nothing changed since; "
                "run named cases or change something first." % (name, where))
    return None


def release_branches(root: Path) -> list[str]:
    try:
        data = json.loads((root / "tools" / "change-notes.json").read_text(encoding="utf-8"))
        value = data.get("release_branches")
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            return value
    except (OSError, ValueError, AttributeError):
        pass
    return list(DEFAULT_RELEASE_BRANCHES)


def current_branch(root: Path) -> str:
    return rs.git(["rev-parse", "--abbrev-ref", "HEAD"], root)[1]


def option(args: list[str], *names: str) -> str | None:
    for i, a in enumerate(args):
        if a in names and i + 1 < len(args):
            return args[i + 1]
        for n in names:
            if n.startswith("--") and a.startswith(n + "="):
                return a[len(n) + 1:]
    return None


def check_pr(root: Path, toks: list[str]) -> str | None:
    if len(toks) < 3 or toks[0] != "gh" or toks[1] != "pr" or toks[2] not in ("create", "ready"):
        return None
    verb, args = toks[2], toks[3:]
    if verb == "create" and any(a in ("--draft", "-d") for a in args):
        return None
    if "--undo" in args:
        return None  # gh pr ready --undo returns a PR to draft
    head = option(args, "--head", "-H")
    if head is None and verb == "ready":
        target = next((a for a in args if not a.startswith("-")), None)
        if target:
            try:
                p = subprocess.run(["gh", "pr", "view", target, "--json", "headRefName", "-q", ".headRefName"],
                                   cwd=root, capture_output=True, text=True, timeout=15)
                head = p.stdout.strip() or None
            except (OSError, subprocess.TimeoutExpired):
                head = None
    head = (head or current_branch(root)).split(":")[-1]
    patterns = release_branches(root)
    if any(fnmatch.fnmatchcase(head, g) for g in patterns):
        return None
    return ("%s is not a release branch (%s), so no ready pull request may come from it. "
            "Open a draft instead: gh pr create --draft. The ready pull request goes from the "
            "integration branch once the train is joined (scripts/delivery/join.py)."
            % (head or "this branch", ", ".join(patterns)))


def check(command: str, cwd: str | None = None) -> str | None:
    root = rs.repo_root(cwd)
    for toks in segments(command):
        reason = check_pr(root, toks) or check_tests(root, toks)
        if reason:
            return reason
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["--check"]:
            command, cwd = " ".join(argv[1:]), None
        else:
            data = json.loads(sys.stdin.read() or "{}")
            if data.get("tool_name", "Bash") != "Bash":
                return 0
            command = (data.get("tool_input") or {}).get("command") or ""
            cwd = data.get("cwd")
        reason = check(command, cwd)
    except Exception as exc:  # a broken guard must not wedge the session
        print("session_guard: could not decide (%s); allowing" % exc, file=sys.stderr)
        return 1
    if reason:
        print("session_guard: refused. " + reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
