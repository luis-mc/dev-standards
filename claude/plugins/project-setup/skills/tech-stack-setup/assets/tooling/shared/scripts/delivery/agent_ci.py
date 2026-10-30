#!/usr/bin/env python3
"""Start one CI run on each agent branch whose report says CODE DONE (DELIVERYSPEC DL-81; DS26).

Agents keep draft pull requests, which run no CI. When an agent has pushed its code it writes a line `CODE DONE`
in its report (default `docs/agents/reports/{task}.md`); this script starts the CI workflow on that branch
(`gh workflow run <workflow> --ref <branch>`, a `workflow_dispatch` run) once per head commit. CI then plans what
the branch brings since the default branch (`origin/<default>...HEAD`, see ci_scope.py), and that run is the
agent's gate: the agent runs its touched tests and the fast guards, pushes, writes CODE DONE, and does not run
the full local gate.

    agent_ci.py                      # one pass
    agent_ci.py --watch 60           # a pass every 60 s
    agent_ci.py --dry-run            # list what would start

Settings (flags, or the `agent_ci` object of scripts/delivery/ci-scope.json):
    workflow       ci.yml
    branch_prefix  claude/            agent branches are origin/<prefix>*
    report         docs/agents/reports/{task}.md     {task} = the branch name after the prefix, up to the first '-'
    marker         ^\\s*CODE DONE\\b   regex, matched per line

A branch is skipped when its report is missing, lacks the marker, or a `workflow_dispatch` run already exists for
its head. If gh cannot say, nothing is started. Exit 0; 2 for usage. Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULTS = {"workflow": "ci.yml", "branch_prefix": "claude/", "report": "docs/agents/reports/{task}.md",
            "marker": r"^\s*CODE DONE\b"}
CONFIG = "scripts/delivery/ci-scope.json"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout


def settings(path: str = CONFIG) -> dict:
    out = dict(DEFAULTS)
    try:
        out.update((json.loads(Path(path).read_text(encoding="utf-8")).get("agent_ci") or {}))
    except (OSError, ValueError):
        pass
    return out


def branches(prefix: str) -> list[str]:
    out = git("for-each-ref", "--format=%(refname:short)", f"refs/remotes/origin/{prefix}")
    return [b.removeprefix("origin/") for b in out.split() if b]


def task_of(branch: str, prefix: str) -> str:
    return branch.removeprefix(prefix).split("-", 1)[0]


def report_says_done(branch: str, cfg: dict) -> bool:
    path = cfg["report"].format(task=task_of(branch, cfg["branch_prefix"]))
    text = git("show", f"origin/{branch}:{path}")
    return re.search(cfg["marker"], text, re.MULTILINE) is not None


def started_for(branch: str, sha: str, workflow: str) -> bool:
    out = subprocess.run(
        ["gh", "run", "list", "--workflow", workflow, "--branch", branch, "--event", "workflow_dispatch",
         "--limit", "20", "--json", "headSha"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    try:
        return any(r.get("headSha") == sha for r in json.loads(out or "[]"))
    except (json.JSONDecodeError, AttributeError):
        return True  # unsure: never start a second run


def one_pass(cfg: dict, dry_run: bool = False) -> list[str]:
    git("fetch", "-q", "--prune", "origin")
    started = []
    for branch in branches(cfg["branch_prefix"]):
        sha = git("rev-parse", f"origin/{branch}").strip()
        if not sha or not report_says_done(branch, cfg) or started_for(branch, sha, cfg["workflow"]):
            continue
        stamp = time.strftime("%H:%M")
        if dry_run:
            print(f"{stamp} would start CI on {branch} ({sha[:9]})", flush=True)
        else:
            r = subprocess.run(["gh", "workflow", "run", cfg["workflow"], "--ref", branch],
                               capture_output=True, text=True)
            print(f"{stamp} CI started on {branch} ({sha[:9]})" if r.returncode == 0
                  else f"{stamp} could not start CI on {branch}: {r.stderr.strip()}", flush=True)
        started.append(branch)
    return started


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--watch", type=int, default=0, help="seconds between passes; 0 = one pass")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--config", default=CONFIG)
    for k in DEFAULTS:
        p.add_argument(f"--{k.replace('_', '-')}")
    a = p.parse_args(argv)
    cfg = settings(a.config)
    cfg.update({k: getattr(a, k) for k in DEFAULTS if getattr(a, k)})
    while True:
        one_pass(cfg, a.dry_run)
        if a.watch <= 0:
            return 0
        time.sleep(a.watch)


if __name__ == "__main__":
    sys.exit(main())
