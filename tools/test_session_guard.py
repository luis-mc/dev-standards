#!/usr/bin/env python3
"""Tests for session_guard.py and run_suite.py (STACKSPEC 13.8).

    python tools/test_session_guard.py [CASE ...]     cases whose name contains an argument

Each case builds a tiny git repository in a temporary directory; none runs a real suite.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DELIVERY = ROOT / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery"
SETTINGS = ROOT / "claude/plugins/project-setup/skills/claude-setup/assets/.claude/settings.json"
sys.path.insert(0, str(DELIVERY))
sys.dont_write_bytecode = True

import run_suite as rs  # noqa: E402
import session_guard as sg  # noqa: E402

TESTS: list = []
PY = "python"


def case(fn):
    TESTS.append(fn)
    return fn


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def make_repo(suites: list[dict] | None = None, branch: str = "main", notes: dict | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="sg-")).resolve()
    git(d, "init", "-q", "-b", branch)
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / ".gitignore").write_text(".delivery/\n")
    if suites is not None:
        (d / "scripts/delivery").mkdir(parents=True)
        (d / "scripts/delivery/suites.json").write_text(json.dumps({"schema": 1, "suites": suites}))
    if notes is not None:
        (d / "tools").mkdir()
        (d / "tools/change-notes.json").write_text(json.dumps(notes))
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "init")
    return d


SUITES = [
    {"name": "unit", "full": "python tests/run.py", "cases": "python tests/run.py -k {cases}", "full_args": ["--fast"]},
    {"name": "e2e", "full": "pnpm e2e", "cases": "pnpm e2e -g {cases}"},
    {"name": "slow", "full": "python tests/slow.py", "cases": "", "measure": False},
]


def refused(root: Path, command: str) -> str | None:
    return sg.check(command, str(root))


def stamp(root: Path, name: str, seconds: float, kind: str = "local", passed: bool = True,
          days_old: float = 0, tree: str | None = "same") -> None:
    data = rs.read_times(root)
    when = (datetime.now(timezone.utc) - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data[kind][name] = {"seconds": seconds, "at": when, "passed": passed, "machine": rs.socket.gethostname(),
                        "tree": rs.tree_id(root) if tree == "same" else tree}
    rs.write_times(root, data)


@case
def unmeasured_suite_is_heavy():
    r = make_repo(SUITES)
    why = refused(r, "python tests/run.py")
    assert why and "heavy" in why and "--measure unit" in why, why
    assert refused(r, "cd x && pnpm e2e 2>&1 | tail"), "found inside a pipeline"
    assert refused(r, "rtk timeout 900 python3 ./tests/run.py --fast"), "noise and full_args are ignored"
    assert refused(r, "python tests/run.py\n") is not None


@case
def named_cases_always_allowed():
    r = make_repo(SUITES)
    assert refused(r, "python tests/run.py -k login") is None
    assert refused(r, "pnpm e2e -g checkout") is None
    assert refused(r, "python tests/run.py tests/test_a.py") is None
    assert refused(r, "python %s unit login" % (DELIVERY / "run_suite.py")) is None
    assert refused(r, "git status") is None and refused(r, "ls && echo hi") is None


@case
def measured_light_suite_runs_once_per_tree():
    r = make_repo(SUITES)
    stamp(r, "unit", 40, tree=None)
    assert refused(r, "python tests/run.py") is None, "light and unproven"
    stamp(r, "unit", 40)
    why = refused(r, "python tests/run.py")
    assert why and "already passed" in why and "local" in why, why
    (r / "new.txt").write_text("x")
    assert refused(r, "python tests/run.py") is None, "untracked file: the tree is unknown, allowed"
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "change")
    assert refused(r, "python tests/run.py") is None, "a new tree"
    stamp(r, "unit", 40, passed=False)
    assert refused(r, "python tests/run.py") is None, "a failed run does not count"


@case
def ci_record_on_same_tree_refuses():
    r = make_repo(SUITES)
    stamp(r, "unit", 40, tree=None)
    stamp(r, "unit", 400, kind="ci")
    why = refused(r, "python tests/run.py")
    assert why and "CI" in why, why
    stamp(r, "unit", 400, kind="ci", passed=False)
    assert refused(r, "python tests/run.py") is None


@case
def over_three_minutes_is_heavy():
    r = make_repo(SUITES)
    stamp(r, "unit", 181, tree=None)
    why = refused(r, "python tests/run.py")
    assert why and "181" in why and "180" in why, why
    stamp(r, "unit", 180, tree=None)
    assert refused(r, "python tests/run.py") is None


@case
def run_suite_form_is_recognised():
    r = make_repo(SUITES)
    tool = "python %s" % (DELIVERY / "run_suite.py")
    assert refused(r, tool + " unit"), "unmeasured, through run_suite.py"
    stamp(r, "unit", 5)
    assert refused(r, tool + " unit"), "same tree through run_suite.py"
    assert refused(r, tool + " --list") is None
    assert refused(r, tool + " unit login") is None


@case
def measure_rules():
    r = make_repo(SUITES)
    tool = "python %s --measure " % (DELIVERY / "run_suite.py")
    assert refused(r, tool + "unit") is None, "no measurement yet"
    stamp(r, "unit", 50, days_old=29)
    why = refused(r, tool + "unit")
    assert why and "29 days" in why, why
    stamp(r, "unit", 50, days_old=31)
    assert refused(r, tool + "unit") is None, "older than 30 days"
    why = refused(r, tool + "slow")
    assert why and "measure=false" in why, why
    assert refused(r, tool + "nosuch") is None


@case
def measure_false_suite_stays_heavy():
    r = make_repo(SUITES)
    stamp(r, "slow", 5)
    why = refused(r, "python tests/slow.py")
    assert why and "measure=false" in why, why


@case
def no_suites_no_refusal():
    r = make_repo(None)
    assert refused(r, "python tests/run.py") is None
    assert refused(r, "pnpm e2e") is None


@case
def draft_prs_allowed_ready_only_from_release_branches():
    r = make_repo(None, branch="TC9-guards")
    assert refused(r, "gh pr create --draft --base x-integration") is None
    assert refused(r, "gh pr create -d --title t") is None
    why = refused(r, "gh pr create --title t")
    assert why and "TC9-guards" in why and "*-integration" in why and "--draft" in why, why
    assert refused(r, "gh pr ready")
    assert refused(r, "gh pr ready --undo") is None
    assert refused(r, "git push && gh pr create --fill")
    assert refused(r, "gh pr create --head DS55-integration --fill") is None
    assert refused(r, "gh pr create --head=other:feat/x --fill")
    assert refused(r, "gh pr list") is None and refused(r, "gh pr view 3") is None
    git(r, "checkout", "-q", "-b", "DS55-integration")
    assert refused(r, "gh pr create --fill") is None
    assert refused(r, "gh pr ready") is None


@case
def release_branches_come_from_change_notes_json():
    r = make_repo(None, branch="release/1", notes={"release_branches": ["release/*"]})
    assert refused(r, "gh pr create --fill") is None
    git(r, "checkout", "-q", "-b", "DS1-integration")
    assert refused(r, "gh pr create --fill"), "the file replaces the default"


@case
def hook_protocol_exit_codes():
    r = make_repo(SUITES, branch="T1-x")
    script = str(DELIVERY / "session_guard.py")

    def hook(command: str, tool: str = "Bash"):
        payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": str(r)})
        return subprocess.run([PY, script], input=payload, capture_output=True, text=True)

    p = hook("python tests/run.py")
    assert p.returncode == 2 and "heavy" in p.stderr and p.stdout == "", (p.returncode, p.stderr)
    assert hook("python tests/run.py -k a").returncode == 0
    assert hook("gh pr create --fill").returncode == 2
    assert hook("python tests/run.py", tool="Read").returncode == 0
    bad = subprocess.run([PY, script], input="not json", capture_output=True, text=True)
    assert bad.returncode == 1 and "could not decide" in bad.stderr, bad.returncode
    assert subprocess.run([PY, script, "--check", "gh pr create"], cwd=r).returncode == 2


@case
def run_suite_runs_and_records():
    cases_script = "import sys; print('CASES', sys.argv[1:])"
    suites = [{"name": "t", "full": '%s -c "print(1)"' % PY,
               "cases": '%s -c "%s" {cases}' % (PY, cases_script)},
              {"name": "bad", "full": '%s -c "raise SystemExit(3)"' % PY}]
    r = make_repo(suites)
    run = [PY, str(DELIVERY / "run_suite.py")]

    def go(*a: str):
        return subprocess.run([*run, *a], cwd=r, capture_output=True, text=True)

    p = go("t")
    assert p.returncode == 0 and "recorded" in p.stdout, p.stdout + p.stderr
    rec = rs.read_times(r)["local"]["t"]
    assert rec["passed"] and rec["seconds"] < 60 and rec["tree"] == git(r, "write-tree"), rec
    assert "light" in go("--list").stdout
    p = go("t", "a b", "c")
    assert p.returncode == 0 and "CASES ['a b', 'c']" in p.stdout, p.stdout + p.stderr
    assert go("bad").returncode == 3 and rs.read_times(r)["local"]["bad"]["passed"] is False
    assert go("nosuch").returncode == 2
    assert go("bad", "x").returncode == 2, "no case command declared"
    assert go("--measure", "t").returncode == 0
    assert go("--record-ci", "t", "--seconds", "12.5").returncode == 0
    assert rs.read_times(r)["ci"]["t"]["seconds"] == 12.5
    assert (r / ".delivery/suite-times.json").is_file() and git(r, "status", "--porcelain") == ""


@case
def ci_step_times_are_recorded_apart():
    suites = [{"name": "unit", "full": "x", "ci_step": "Unit tests"}, {"name": "other", "full": "y"}]
    r = make_repo(suites)
    head = git(r, "rev-parse", "HEAD")
    jobs = [{"steps": [
        {"name": "Setup", "startedAt": "2026-01-01T00:00:00Z", "completedAt": "2026-01-01T00:00:05Z",
         "conclusion": "success"},
        {"name": "unit tests", "startedAt": "2026-01-01T00:00:05Z", "completedAt": "2026-01-01T00:02:05Z",
         "conclusion": "failure"}]}]
    rs.record_ci_times(r, {"headSha": head}, jobs)
    data = rs.read_times(r)
    assert data["local"] == {} and set(data["ci"]) == {"unit"}, data
    assert data["ci"]["unit"]["seconds"] == 120 and data["ci"]["unit"]["passed"] is False
    assert data["ci"]["unit"]["tree"] == git(r, "rev-parse", "HEAD^{tree}")


@case
def suites_file_locations():
    r = make_repo(None)
    assert rs.load_suites(r) == {}
    (r / ".claude").mkdir()
    (r / ".claude/suites.json").write_text(json.dumps({"suites": [{"name": "a", "full": "echo a"}]}))
    assert list(rs.load_suites(r)) == ["a"]
    (r / "other.json").write_text(json.dumps({"suites": [{"name": "b", "full": "echo b"}]}))
    os.environ["SUITES_JSON"] = "other.json"
    try:
        assert list(rs.load_suites(r)) == ["b"]
    finally:
        del os.environ["SUITES_JSON"]


@case
def template_settings_register_a_guarded_hook():
    cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
    entry = cfg["hooks"]["PreToolUse"][0]
    cmd = entry["hooks"][0]["command"]
    assert entry["matcher"] == "Bash" and "scripts/delivery/session_guard.py" in cmd
    assert cmd.startswith('[ -f "$CLAUDE_PROJECT_DIR/scripts/delivery/session_guard.py" ] || exit 0'), cmd


@case
def this_repo_registers_the_hook_and_declares_suites():
    cfg = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    cmd = cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "tooling/shared/scripts/delivery/session_guard.py" in cmd
    suites = rs.load_suites(ROOT)
    on_disk = {p.stem for p in (ROOT / "tools").glob("test_*.py")}
    declared = {Path(s["full"].split()[1]).stem for s in suites.values()}
    assert on_disk == declared, (on_disk ^ declared)
    for name in ("project-artifacts", "project-artifacts-hooks",
                 "delivery-gate", "delivery-cleanup", "delivery-ci"):
        assert suites[name]["measure"] is False, name
    for s in suites.values():
        if s["cases"]:
            assert "{cases}" in s["cases"], s["name"]


def main() -> int:
    only = sys.argv[1:]
    chosen = [f for f in TESTS if not only or any(o in f.__name__ for o in only)]
    failed = 0
    for fn in chosen:
        try:
            fn()
        except Exception:  # noqa: BLE001 - report every failing case
            failed += 1
            print("FAIL  %s\n      %s" % (fn.__name__, traceback.format_exc().strip().replace("\n", "\n      ")))
        else:
            print("ok    %s" % fn.__name__)
    print("\n%d cases, %d failed" % (len(chosen), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
