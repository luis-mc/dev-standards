#!/usr/bin/env python3
"""Regression tests for the DL56 fixes in the shared delivery scripts (F12-F19).

    python3 tools/test_delivery_shared_fixes.py [-k SUBSTRING]

Each case builds a tiny git repository in a temporary directory.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DS = ROOT / "claude/plugins/delivery/templates/shared/scripts/delivery"
sys.path.insert(0, str(DS))
sys.dont_write_bytecode = True

import area_select as asel  # noqa: E402
import change_notes as cn  # noqa: E402
import ci_scope as cs  # noqa: E402
import delivery_common as dc  # noqa: E402
import runner_plan as rp  # noqa: E402
import session_guard as sg  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def git(cwd, *args):
    return subprocess.run(["git", "-c", "core.quotePath=true", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


def repo(files: dict, branch="main") -> Path:
    d = Path(tempfile.mkdtemp(prefix="dl56-")).resolve()
    git(d, "init", "-q", "-b", branch)
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    for p, text in files.items():
        (d / p).parent.mkdir(parents=True, exist_ok=True)
        (d / p).write_text(text, encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "init")
    return d


def in_dir(d: Path, fn, *a):
    old = os.getcwd()
    os.chdir(d)
    try:
        return fn(*a)
    finally:
        os.chdir(old)


@case
def f12_rename_counts_old_path():
    d = repo({"apps/api/src/price.ts": "x\n", "apps/web/a.ts": "y\n"})
    git(d, "branch", "base")
    git(d, "checkout", "-q", "-b", "work")
    (d / "scripts/ci").mkdir(parents=True)
    git(d, "mv", "apps/api/src/price.ts", "scripts/ci/price.ts")
    git(d, "commit", "-q", "-m", "move")
    for fn in (cs.changed_from_git, asel.changed_from_git):
        got = in_dir(d, fn, "base")
        assert "apps/api/src/price.ts" in got and "scripts/ci/price.ts" in got, (fn.__module__, got)


@case
def f16_non_ascii_names_are_real():
    d = repo({"a.txt": "x\n"})
    git(d, "branch", "base")
    git(d, "checkout", "-q", "-b", "work")
    (d / "docs").mkdir()
    (d / "docs/café.md").write_text("hi\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "cafe")
    for fn in (cs.changed_from_git, asel.changed_from_git):
        got = in_dir(d, fn, "base")
        assert got == ["docs/café.md"], (fn.__module__, got)


@case
def f19_dirty_paths_whole_paths():
    d = repo({"zfile": "x\n", ".delivery/ledger.json": "{}\n"})
    (d / "zfile").write_text("changed\n")
    (d / ".delivery/ledger.json").write_text("{\"a\":1}\n")
    assert dc.dirty_paths(d) == ["zfile"], dc.dirty_paths(d)
    (d / ".delivery/ledger.json").write_text("{}\n")
    git(d, "checkout", "-q", "zfile")
    (d / "new file.txt").write_text("n\n")
    assert dc.dirty_paths(d) == ["new file.txt"], dc.dirty_paths(d)


@case
def f14_removed_rule_line_is_reported():
    text = "# T\n\n## What changed\n\nold\n\n---\n\nmore\n"
    d = repo({"s.md": text})
    git(d, "branch", "base")
    git(d, "checkout", "-q", "-b", "work")
    (d / "s.md").write_text(text.replace("---\n\n", "").replace("more", "more2"))
    git(d, "commit", "-qam", "edit")
    removed, added = cn.changed_lines(d, "base", "s.md")
    assert (7, "---") in removed, removed
    assert (9, "more") in removed and added, (removed, added)


def bare_plan(label: str, alive: bool):
    root = tempfile.mkdtemp(prefix="dl56-lock-")
    plan = rp.Plan.__new__(rp.Plan)
    plan.lock_path = os.path.join(root, ".delivery", rp.LOCK_NAME)
    plan.alive = lambda pid: alive
    plan.label, plan.job_id, plan.have_lock = label, label + "-1", False
    return plan


@case
def f15_half_written_lock_is_not_dead():
    plan = bare_plan("b", alive=False)
    os.makedirs(os.path.dirname(plan.lock_path))
    open(plan.lock_path, "w").close()          # A created it, has not written yet
    why = plan.lock_blocker()
    assert why and not plan.have_lock, (why, plan.have_lock)
    assert os.path.exists(plan.lock_path)


@case
def f15_lock_is_complete_when_visible():
    plan = bare_plan("a", alive=True)
    assert plan.lock_blocker() is None and plan.have_lock
    assert json.load(open(plan.lock_path))["job"] == "a-1"
    assert os.listdir(os.path.dirname(plan.lock_path)) == [rp.LOCK_NAME]


def guard_repo(branch="T1-feature") -> Path:
    return repo({"a": "x\n"}, branch=branch)


@case
def f13_quoted_gh_pr_create_is_not_a_command():
    d = guard_repo()
    for cmd in ['git commit -m "docs; gh pr create later"',
                'echo "next step && gh pr create --fill"',
                "cat <<'EOF'\nfirst\ngh pr create --fill\nEOF"]:
        assert sg.check(cmd, str(d)) is None, cmd
    assert sg.check("gh pr create --fill", str(d)), "a real one is still refused"
    assert sg.check("echo hi && gh pr create --fill", str(d))


@case
def f17_measure_equals_form_is_checked():
    d = repo({"scripts/delivery/suites.json": json.dumps(
        {"schema": 1, "suites": [{"name": "e2e", "full": "pnpm e2e", "cases": "pnpm e2e -g {cases}", "measure": False}]})})
    a = sg.check("python3 scripts/delivery/run_suite.py --measure e2e", str(d))
    b = sg.check("python3 scripts/delivery/run_suite.py --measure=e2e", str(d))
    assert a and b == a, (a, b)


@case
def f18_draft_equals_true_is_a_draft():
    d = guard_repo()
    assert sg.check("gh pr create --draft=true --fill", str(d)) is None
    assert sg.check("gh pr create --draft=1 --fill", str(d)) is None
    assert sg.check("gh pr create --draft=false --fill", str(d))
    assert sg.check("gh pr create --draft --fill", str(d)) is None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="")
    args = ap.parse_args()
    failed = 0
    for fn in CASES:
        if args.k and args.k not in fn.__name__:
            continue
        try:
            fn()
            print("PASS  " + fn.__name__)
        except Exception:
            failed += 1
            print("FAIL  " + fn.__name__)
            traceback.print_exc()
    print("%d failed" % failed if failed else "all passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
