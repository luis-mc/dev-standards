#!/usr/bin/env python3
"""Start one CI run on each agent branch whose report says CODE DONE (DELIVERYSPEC DL-81; DS26).

Agents keep draft pull requests, which run no CI. When an agent has pushed its code it writes a line `CODE DONE`
in its report (default `docs/work/reports/{task}.md`, DOCSPEC R10.1; the old `docs/work/agents/reports/` and
`docs/agents/reports/` are still read while projects migrate). This script merges that branch onto its base without a
checkout (`git merge-tree --write-tree`), pushes the result as a two-parent commit (the branch head first, the base
second) to `ci/<task>`, and starts the CI workflow on that ref (`gh workflow run <workflow> --ref ci/<task>`, a
`workflow_dispatch` run), once per branch head. So the run tests the agent's code on top of the code it will be
joined with (`--base`, default `origin/master`; the orchestrator passes `origin/release/<n>`), and a branch cut before
the workflow had `workflow_dispatch` still gets one. A branch that conflicts with its base is reported by file and
not run. CI plans what the branch brings since the default branch (see ci_scope.py); that run is the agent's gate.
`cleanup.py --pr N` removes the `ci/<task>` refs of a merged train.

    agent_ci.py                              # one pass
    agent_ci.py --watch 60                   # a pass every 60 s
    agent_ci.py --base origin/release/12     # merge onto a release branch
    agent_ci.py --dry-run                    # list what would start (pushes nothing)

Settings (flags, or the `agent_ci` object of scripts/delivery/ci-scope.json):
    workflow       ci.yml
    base           origin/master      ref each branch is merged onto
    branch_prefix  claude/            agent branches are origin/<prefix>*
    ci_prefix      ci/                the merged ref is <ci_prefix><task>
    report         docs/work/reports/{task}.md       {task} = the branch name after the prefix, up to the first '-'
                   (a string, or a list tried in order; any one with the marker counts)
    marker         ^\\s*CODE DONE\\b   regex, matched per line

A branch that changes UI code or e2e specs also needs its e2e record (DELIVERYSPEC DL-87): the agent runs
`scripts/delivery/branch_gate.py --e2e-only` in its sandbox, which publishes the result of the specs mapped to the
screens it changed; without that record for the branch head, no CI is started and the line names the command
(`require_e2e: false` in the `agent_ci` settings turns this off; a repository without gate.json is not held).

A branch is skipped when its report is missing, lacks the marker, or a `workflow_dispatch` run already exists for
its head (unsure: nothing is started). Exit 0; 2 for usage. Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULTS = {"workflow": "ci.yml", "base": "origin/master", "branch_prefix": "claude/", "ci_prefix": "ci/",
            "report": ["docs/work/reports/{task}.md", "docs/work/agents/reports/{task}.md", "docs/agents/reports/{task}.md"],
            "marker": r"^\s*CODE DONE\b", "require_e2e": True}
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


def ci_branch(branch: str, cfg: dict) -> str:
    return cfg["ci_prefix"] + task_of(branch, cfg["branch_prefix"])


LEGACY_REPORTS = ["docs/work/agents/reports/{task}.md", "docs/agents/reports/{task}.md"]


def report_paths(cfg: dict, task: str) -> list[str]:
    """Where the report may be: the configured path(s), then the old locations (during migration to docs/work/reports/).
    A project that set `report` to the previous default string moves with the default."""
    conf = cfg["report"]
    conf = [conf] if isinstance(conf, str) else list(conf)
    if conf == ["docs/agents/reports/{task}.md"]:
        conf = list(DEFAULTS["report"])
    return [p.format(task=task) for p in dict.fromkeys(conf + (LEGACY_REPORTS if conf == DEFAULTS["report"] else []))]


def report_says_done(branch: str, cfg: dict) -> bool:
    task = task_of(branch, cfg["branch_prefix"])
    for path in report_paths(cfg, task):
        text = git("show", f"origin/{branch}:{path}")
        if re.search(cfg["marker"], text, re.MULTILINE) is not None:
            return True
    return False


def ci_ref(branch: str, base: str, cfg: dict, push: bool = True) -> str | None:
    """Merge `origin/<branch>` onto `base` without a checkout, push the two-parent commit to ci/<task> and return
    that name; None when the merge conflicts or the push is refused. With push=False only the merge is checked
    and the name is returned."""
    mt = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", base, f"origin/{branch}"],
                        capture_output=True, text=True, encoding="utf-8")
    lines = mt.stdout.splitlines()
    stamp = time.strftime("%H:%M")
    if mt.returncode != 0:
        # after the tree line come the conflicted file names, a blank line, then informational messages
        files: list[str] = []
        for line in lines[1:]:
            if not line.strip():
                break
            files.append(line.strip())
        detail = ", ".join(files[:5]) or mt.stderr.strip()
        print(f"{stamp} {branch} conflicts with {base}: {detail}", flush=True)
        return None
    name = ci_branch(branch, cfg)
    if not push:
        return name
    commit = subprocess.run(
        ["git", "commit-tree", lines[0].strip(), "-p", f"origin/{branch}", "-p", base,
         "-m", f"Manual CI run of {branch} merged onto {base}"],
        capture_output=True, text=True, encoding="utf-8")
    if commit.returncode != 0:
        print(f"{stamp} could not merge {branch} onto {base}: {commit.stderr.strip()}", flush=True)
        return None
    pushed = subprocess.run(["git", "push", "-q", "-f", "origin", f"{commit.stdout.strip()}:refs/heads/{name}"],
                            capture_output=True, text=True, encoding="utf-8")
    if pushed.returncode != 0:
        tail = "\n".join((pushed.stderr or pushed.stdout).strip().splitlines()[-3:])
        print(f"{stamp} push of {name} refused: {tail}", flush=True)
        return None
    return name


def started_for_ci(branch: str, sha: str, cfg: dict) -> bool:
    """A workflow_dispatch run on ci/<task> whose head commit's first parent is `sha` is already started."""
    out = subprocess.run(
        ["gh", "run", "list", "--workflow", cfg["workflow"], "--branch", ci_branch(branch, cfg), "--event",
         "workflow_dispatch", "--limit", "20", "--json", "headSha"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    try:
        runs = json.loads(out or "[]")
        return any(git("rev-parse", "--verify", "-q", f"{r.get('headSha')}^1").strip() == sha
                   for r in runs if r.get("headSha"))
    except (json.JSONDecodeError, AttributeError):
        return True  # unsure: never start a second run


def e2e_missing(branch: str, base: str) -> list[str]:
    """Reasons the branch's e2e record is not good (gate_verify.e2e_gate_check); [] when none is needed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import gate_verify
        return gate_verify.e2e_gate_check(branch, base, base.split("/", 1)[0] if "/" in base else "origin")
    except Exception as exc:  # unsure: do not hold a branch on a tool error
        print(f"{time.strftime('%H:%M')} {branch}: e2e check unavailable ({exc}); not held", flush=True)
        return []


def one_pass(cfg: dict, dry_run: bool = False) -> list[str]:
    git("fetch", "-q", "--prune", "origin")
    base = cfg["base"]
    started = []
    for branch in branches(cfg["branch_prefix"]):
        sha = git("rev-parse", f"origin/{branch}").strip()
        if not sha or not report_says_done(branch, cfg) or started_for_ci(branch, sha, cfg):
            continue
        if cfg.get("require_e2e", True):
            missing = e2e_missing(branch, base)
            if missing:
                print(f"{time.strftime('%H:%M')} {branch} ({sha[:9]}) waits for its e2e specs: " + "; ".join(missing), flush=True)
                continue
        ref = ci_ref(branch, base, cfg, push=not dry_run)
        if ref is None:
            continue
        stamp = time.strftime("%H:%M")
        if dry_run:
            print(f"{stamp} would start CI on {ref} = {branch} ({sha[:9]}) + {base}", flush=True)
        else:
            r = subprocess.run(["gh", "workflow", "run", cfg["workflow"], "--ref", ref],
                               capture_output=True, text=True)
            print(f"{stamp} CI started on {ref} = {branch} ({sha[:9]}) + {base}" if r.returncode == 0
                  else f"{stamp} could not start CI on {ref}: {r.stderr.strip()}", flush=True)
        started.append(branch)
    return started


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--watch", type=int, default=0, help="seconds between passes; 0 = one pass")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--config", default=CONFIG)
    for k in DEFAULTS:
        if k != "require_e2e":
            p.add_argument(f"--{k.replace('_', '-')}")
    a = p.parse_args(argv)
    cfg = settings(a.config)
    cfg.update({k: getattr(a, k) for k in DEFAULTS if k != "require_e2e" and getattr(a, k)})
    while True:
        one_pass(cfg, a.dry_run)
        if a.watch <= 0:
            return 0
        time.sleep(a.watch)


if __name__ == "__main__":
    sys.exit(main())
