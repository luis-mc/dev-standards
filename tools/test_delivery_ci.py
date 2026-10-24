#!/usr/bin/env python3
"""Prove the CI-side delivery scripts and workflows do what CONTRACT.md says.

Three groups, each built so that a check which stops working fails here instead
of going quiet:

  * ci_watch.py and ci_skip_check.py run against a stub `gh` on PATH that answers
    from a JSON fixture per test. Every case has a contrast case that must give
    the opposite answer (success vs failure, trees equal vs different), and the
    stub itself fails loudly if `gh pr ...` is ever called.
  * reach_check.py runs against an http.server on localhost.
  * the four ci.yml files, the Playwright config and the tooling README are
    checked structurally (text and regex, no YAML library). The checker is run on
    deliberately broken copies and must report each defect. That covers the
    runs-on expression (U5), the concurrency block (U8) and the pinned gitleaks
    checksum step (U4); the two shared workflows are checked for runs-on too.
  * tools_pin.py runs against a local checksums file, and agent_setup.sh against
    a local http.server holding a fake release, to prove the pinned SHA-256 is what
    the archive is checked against (the checksums file is never fetched), that the
    old tools.json form still works with a warning, and that the checks can fail
    (a tampered archive, a script with the comparison removed).

Run:  python3 tools/test_delivery_ci.py
"""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import traceback
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLING = (ROOT / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling")
DELIVERY = TOOLING / "shared/scripts/delivery"
CI_WATCH = DELIVERY / "ci_watch.py"
CI_SKIP = DELIVERY / "ci_skip_check.py"
REACH = DELIVERY / "reach_check.py"
TOOLS_PIN = DELIVERY / "tools_pin.py"
AGENT_SETUP = DELIVERY / "agent_setup.sh"
SHARED_WORKFLOWS = ("artifact-prune.yml", "train-cleanup.yml")
TRACKS = ("ts", "go", "rust", "dotnet")

SHA = "a" * 40

# ---------------------------------------------------------------------------
# Stub gh
# ---------------------------------------------------------------------------

STUB_GH = r'''
import json, os, sys

argv = sys.argv[1:]
log = os.environ.get("GH_STUB_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\n")


def fail(msg, code=1):
    sys.stderr.write(msg + "\n")
    sys.exit(code)


if argv[:1] == ["pr"]:
    fail("stub gh: `gh pr ...` must never be called by the CI scripts (13.6)", 97)

fixture_path = os.environ["GH_STUB_FIXTURE"]
with open(fixture_path, encoding="utf-8") as fh:
    fx = json.load(fh)


def bump():
    state = fixture_path + ".calls"
    n = 0
    if os.path.exists(state):
        n = int(open(state).read() or 0)
    open(state, "w").write(str(n + 1))
    return n


if argv[:2] == ["run", "list"]:
    if fx.get("run_list_error"):
        fail("HTTP 502: bad gateway")
    seq = fx["run_list"]
    resp = seq[min(bump(), len(seq) - 1)]
    wf = argv[argv.index("--workflow") + 1] if "--workflow" in argv else None
    out = [{k: v for k, v in r.items() if k != "_workflow"}
           for r in resp if wf is None or r.get("_workflow", wf) == wf]
    print(json.dumps(out))
elif argv[:2] == ["run", "view"]:
    print(json.dumps(fx["run_view"][argv[2]]))
elif argv[:1] == ["api"]:
    path, fields, i = None, [], 1
    while i < len(argv):
        a = argv[i]
        if a in ("-H", "--method", "-X"):
            i += 2
        elif a == "-f":
            fields.append(argv[i + 1].split("=", 1))
            i += 2
        else:
            path = a
            i += 1
    key = path + ("?" + "&".join(f"{k}={v}" for k, v in fields) if fields else "")
    if key not in fx.get("api", {}):
        fail("stub gh: no fixture for " + key)
    resp = fx["api"][key]
    if isinstance(resp, dict) and "__error" in resp:
        fail(resp["__error"])
    print(json.dumps(resp))
else:
    fail("stub gh: unexpected call " + " ".join(argv))
'''


class Sandbox:
    """A temp dir holding a stub `gh` (script + shim) and a fixture."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ds9-")
        self.dir = Path(self._tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        (self.bin / "gh.py").write_text(STUB_GH, encoding="utf-8")
        if os.name == "nt":
            (self.bin / "gh.cmd").write_text(
                f'@"{sys.executable}" "%~dp0gh.py" %*\r\n', encoding="utf-8")
        else:
            shim = self.bin / "gh"
            shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/gh.py" "$@"\n',
                            encoding="utf-8")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.fixture = self.dir / "fixture.json"
        self.log = self.dir / "gh.log"
        self.write_fixture({})

    def write_fixture(self, fx: dict) -> None:
        self.fixture.write_text(json.dumps(fx), encoding="utf-8")

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def env(self, extra: dict | None = None, with_stub: bool = True) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GITHUB_") and k not in ("GH_TOKEN", "GITHUB_TOKEN")}
        env["PYTHONUTF8"] = "1"
        if with_stub:
            env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        else:
            empty = self.dir / "empty"
            empty.mkdir(exist_ok=True)
            env["PATH"] = str(empty)
        env["GH_STUB_FIXTURE"] = str(self.fixture)
        env["GH_STUB_LOG"] = str(self.log)
        env.update(extra or {})
        return env

    def run(self, script: Path, args: list[str], *, env_extra: dict | None = None,
            cwd: Path | None = None, with_stub: bool = True) -> tuple[int, str, str]:
        proc = subprocess.run(
            [sys.executable, "-I", str(script), *args], cwd=cwd or self.dir,
            env=self.env(env_extra, with_stub), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)
        return proc.returncode, proc.stdout, proc.stderr

    def close(self) -> None:
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def expect_exit(got: int, want: int, out: str, err: str) -> None:
    check(got == want, f"exit {got}, wanted {want}\nstdout: {out}\nstderr: {err}")


# ---------------------------------------------------------------------------
# ci_watch
# ---------------------------------------------------------------------------

def run_obj(rid: int, status: str, conclusion: str, wf: str = "ci.yml") -> dict:
    return {"databaseId": rid, "workflowName": "CI", "status": status,
            "conclusion": conclusion, "event": "pull_request", "headSha": SHA,
            "_workflow": wf}


WATCH_FAST = ["--interval", "0.05", "--timeout", "20"]


def watch(sb: Sandbox, fx: dict, extra: list[str] | None = None, **kw):
    sb.write_fixture(fx)
    return sb.run(CI_WATCH, [SHA, *(extra or WATCH_FAST)], **kw)


@test
def watch_success():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "completed", "success")]]})
        expect_exit(rc, 0, out, err)
        calls = sb.calls()
        check(calls and calls[0][:2] == ["run", "list"] and "--commit" in calls[0],
              f"expected `gh run list --commit`, got {calls}")
    finally:
        sb.close()


@test
def watch_skipped_counts_as_success():
    sb = Sandbox()
    try:
        # No open pull request for the head (plain branch): skipped keeps counting as success.
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "completed", "skipped")]],
                                  "api": {PULLS_PATH: []}})
        expect_exit(rc, 0, out, err)
    finally:
        sb.close()


PULLS_PATH = "repos/{owner}/{repo}/commits/" + SHA + "/pulls"
OPEN_PR = [{"number": 5, "state": "open", "head": {"sha": SHA}}]


def push_skipped(rid: int = 1) -> dict:
    return {**run_obj(rid, "completed", "success"), "event": "push"}


SKIPPED_JOBS = {"jobs": [{"name": "gate", "conclusion": "skipped", "steps": []},
                         {"name": "tests", "conclusion": "skipped", "steps": []}]}


@test
def watch_pr_head_push_skipped_and_pr_queued_keeps_waiting():
    sb = Sandbox()
    try:
        # A push run with every job skipped, the pull_request run not created, then queued:
        # never green while no job has executed.
        fx = {"run_list": [[push_skipped()], [push_skipped(), run_obj(2, "queued", "")],
                           [push_skipped(), run_obj(2, "completed", "success")]],
              "run_view": {"1": SKIPPED_JOBS}, "api": {PULLS_PATH: OPEN_PR}}
        rc, out, err = watch(sb, fx)
        expect_exit(rc, 0, out, err)
        check("no real run yet" in out, f"did not say it was waiting for a real run: {out}")
        check(len([c for c in sb.calls() if c[:2] == ["run", "list"]]) == 3,
              "did not keep waiting through the skipped and queued polls")
    finally:
        sb.close()


@test
def watch_pr_head_only_skipped_runs_time_out_with_clear_message():
    sb = Sandbox()
    try:
        fx = {"run_list": [[push_skipped()]], "run_view": {"1": SKIPPED_JOBS},
              "api": {PULLS_PATH: OPEN_PR}}
        rc, out, err = watch(sb, fx, ["--interval", "0.1", "--timeout", "1"])
        expect_exit(rc, 4, out, err)
        check("no real run yet" in err, f"timeout message unclear: {err}")
        # Same run with no open PR (a plain branch): the old behaviour, green.
        sb2 = Sandbox()
        try:
            fx["api"] = {PULLS_PATH: []}
            rc2, out2, err2 = watch(sb2, fx)
            expect_exit(rc2, 0, out2, err2)
        finally:
            sb2.close()
    finally:
        sb.close()


@test
def watch_pr_head_push_skipped_and_pr_success_is_green():
    sb = Sandbox()
    try:
        fx = {"run_list": [[push_skipped(), run_obj(2, "completed", "success")]],
              "run_view": {"1": SKIPPED_JOBS}, "api": {PULLS_PATH: OPEN_PR}}
        rc, out, err = watch(sb, fx)
        expect_exit(rc, 0, out, err)
    finally:
        sb.close()


@test
def watch_pr_head_pr_run_failure_is_red():
    sb = Sandbox()
    try:
        fx = {"run_list": [[push_skipped(), run_obj(2, "completed", "failure")]],
              "run_view": {"1": SKIPPED_JOBS, "2": {"jobs": []}}, "api": {PULLS_PATH: OPEN_PR}}
        rc, out, err = watch(sb, fx)
        expect_exit(rc, 1, out, err)
    finally:
        sb.close()


@test
def watch_push_run_that_executed_jobs_is_green_without_pr_lookup():
    sb = Sandbox()
    try:
        ran = {"jobs": [{"name": "tests", "conclusion": "success", "steps": []}]}
        rc, out, err = watch(sb, {"run_list": [[push_skipped()]], "run_view": {"1": ran}})
        expect_exit(rc, 0, out, err)
        check(not any(c[:1] == ["api"] for c in sb.calls()), "looked up PRs for a run that ran jobs")
    finally:
        sb.close()


@test
def watch_failure_prints_failed_jobs():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {
            "run_list": [[run_obj(7, "completed", "failure")]],
            "run_view": {"7": {"jobs": [
                {"name": "lint, types", "conclusion": "failure",
                 "steps": [{"name": "Typecheck", "conclusion": "failure"}]},
                {"name": "integration", "conclusion": "success", "steps": []}]}}})
        expect_exit(rc, 1, out, err)
        check("lint, types" in out and "Typecheck" in out, f"failed job not printed: {out}")
        check("integration" not in out.replace("FAILED", ""), "a passing job was listed as failed")
        check(any(c[:2] == ["run", "view"] and "--json" in c for c in sb.calls()),
              "did not call `gh run view --json jobs`")
    finally:
        sb.close()


@test
def watch_cancelled_is_failure():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[run_obj(7, "completed", "cancelled")]],
                                  "run_view": {"7": {"jobs": []}}})
        expect_exit(rc, 1, out, err)
    finally:
        sb.close()


@test
def watch_any_failed_run_fails_even_if_another_passed():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {
            "run_list": [[run_obj(1, "completed", "success"), run_obj(2, "completed", "failure")]],
            "run_view": {"2": {"jobs": []}}})
        expect_exit(rc, 1, out, err)
    finally:
        sb.close()


@test
def watch_waits_when_no_run_exists_yet():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[], [], [run_obj(1, "completed", "success")]]})
        expect_exit(rc, 0, out, err)
        lists = [c for c in sb.calls() if c[:2] == ["run", "list"]]
        check(len(lists) == 3, f"expected 3 polls (empty, empty, success), got {len(lists)}")
    finally:
        sb.close()


@test
def watch_waits_while_a_run_is_in_progress():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [
            [run_obj(1, "in_progress", ""), run_obj(2, "completed", "success")],
            [run_obj(1, "completed", "success"), run_obj(2, "completed", "success")]]})
        expect_exit(rc, 0, out, err)
        check(len([c for c in sb.calls() if c[:2] == ["run", "list"]]) == 2,
              "did not wait for the in-progress run")
    finally:
        sb.close()


@test
def watch_ignores_runs_of_other_workflows_and_times_out():
    sb = Sandbox()
    try:
        # Only another workflow has a (successful) run: no ci.yml run ever
        # appears, so the answer must be a timeout, never a pass.
        fx = {"run_list": [[run_obj(1, "completed", "success", wf="other.yml")]]}
        rc, out, err = watch(sb, fx, ["--interval", "0.1", "--timeout", "1"])
        expect_exit(rc, 4, out, err)
        # Contrast: the same run belonging to the watched workflow passes.
        sb2 = Sandbox()
        try:
            rc2, out2, err2 = watch(sb2, {"run_list": [[run_obj(1, "completed", "success")]]})
            expect_exit(rc2, 0, out2, err2)
        finally:
            sb2.close()
    finally:
        sb.close()


@test
def watch_workflow_argument_is_passed_to_gh():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "completed", "success", wf="build.yml")]]},
                             [*WATCH_FAST, "--workflow", "build.yml", "--repo", "o/r"])
        expect_exit(rc, 0, out, err)
        first = sb.calls()[0]
        check("build.yml" in first and "o/r" in first, f"--workflow/--repo not forwarded: {first}")
    finally:
        sb.close()


@test
def watch_never_calls_pr_checks():
    sb = Sandbox()
    try:
        for fx, extra in (
            ({"run_list": [[run_obj(1, "completed", "success")]]}, None),
            ({"run_list": [[run_obj(1, "completed", "failure")]], "run_view": {"1": {"jobs": []}}}, None),
            ({"run_list": [[]]}, ["--interval", "0.1", "--timeout", "1"]),
        ):
            watch(sb, fx, extra)
        check(sb.calls(), "no gh calls recorded, the guard below proves nothing")
        check(all(c[0] != "pr" for c in sb.calls()), f"gh pr was called: {sb.calls()}")
        check(all(c[0] == "run" for c in sb.calls()), f"unexpected gh calls: {sb.calls()}")
        # Control: the stub does flag `gh pr checks`, so the assertion above can fail.
        shim = [str(sb.bin / ("gh.cmd" if os.name == "nt" else "gh")), "pr", "checks"]
        proc = subprocess.run(shim, env=sb.env(), capture_output=True, text=True)
        check(proc.returncode == 97, "stub did not reject `gh pr checks`")
        check(["pr", "checks"] in sb.calls(), "stub did not log `gh pr checks`")
    finally:
        sb.close()


@test
def watch_gh_errors_give_up_with_exit_2():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list_error": True})
        expect_exit(rc, 2, out, err)
        check("502" in err, f"gh error not reported: {err}")
    finally:
        sb.close()


@test
def watch_gh_missing_is_exit_2():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "completed", "success")]]},
                             with_stub=False)
        expect_exit(rc, 2, out, err)
        check("gh" in err, f"missing gh not explained: {err}")
    finally:
        sb.close()


@test
def watch_bad_sha_is_exit_2():
    sb = Sandbox()
    try:
        sb.write_fixture({"run_list": [[]]})
        rc, out, err = sb.run(CI_WATCH, ["not-a-sha", *WATCH_FAST])
        expect_exit(rc, 2, out, err)
    finally:
        sb.close()


def timed_job(name: str, start: str, end: str, steps: list | None = None) -> dict:
    return {"name": name, "conclusion": "success", "startedAt": f"2026-10-11T10:{start}Z",
            "completedAt": f"2026-10-11T10:{end}Z", "steps": steps or []}


def step(name: str, start: str, end: str) -> dict:
    return {"name": name, "conclusion": "success", "startedAt": f"2026-10-11T10:{start}Z",
            "completedAt": f"2026-10-11T10:{end}Z"}


SLOW_JOBS = {"jobs": [
    timed_job("lint", "00:00", "01:00"),
    timed_job("e2e", "00:00", "08:00", [
        step("Install", "00:00", "01:00"), step("Playwright", "01:00", "07:30"),
        step("Upload", "07:30", "07:40")])]}


@test
def watch_summary_names_slowest_job_share_and_two_slowest_steps():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "completed", "success")]],
                                  "run_view": {"1": SLOW_JOBS}})
        expect_exit(rc, 0, out, err)
        check("slowest job e2e 8m00s (100% of the run)" in out and "wall 8m00s" in out,
              f"summary lacks the slowest job and its share: {out}")
        check("Playwright 6m30s" in out and "Install 1m00s" in out and "Upload" not in out,
              f"summary should list the two slowest steps only: {out}")
        # Contrast: a shorter slowest job gives a smaller share, so the share is computed.
        sb2 = Sandbox()
        try:
            jobs = {"jobs": [timed_job("lint", "00:00", "02:00"), timed_job("e2e", "00:00", "08:00"),
                             timed_job("late", "08:00", "10:00")]}
            rc2, out2, err2 = watch(sb2, {"run_list": [[run_obj(1, "completed", "success")]],
                                          "run_view": {"1": jobs}})
            expect_exit(rc2, 0, out2, err2)
            check("slowest job e2e 8m00s (80% of the run)" in out2, f"share not computed: {out2}")
        finally:
            sb2.close()
    finally:
        sb.close()


@test
def watch_summary_is_printed_on_failure_without_changing_exit():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[run_obj(7, "completed", "failure")]],
                                  "run_view": {"7": SLOW_JOBS}})
        expect_exit(rc, 1, out, err)
        check("slowest job e2e" in out, f"no summary after a failed run: {out}")
    finally:
        sb.close()


@test
def watch_summary_errors_print_nothing_extra():
    sb = Sandbox()
    try:
        # No run_view fixture: the stub's gh fails; the verdict and exit stay the same.
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "completed", "success")]]})
        expect_exit(rc, 0, out, err)
        check("slowest" not in out, f"summary printed despite an error: {out}")
        # Jobs without times: nothing extra either.
        sb2 = Sandbox()
        try:
            rc2, out2, err2 = watch(sb2, {"run_list": [[run_obj(1, "completed", "success")]],
                                          "run_view": {"1": {"jobs": [{"name": "x", "steps": []}]}}})
            expect_exit(rc2, 0, out2, err2)
            check("slowest" not in out2, f"summary printed without times: {out2}")
        finally:
            sb2.close()
    finally:
        sb.close()


@test
def watch_no_summary_while_runs_are_pending():
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "in_progress", "")]],
                                  "run_view": {"1": SLOW_JOBS}},
                             ["--interval", "0.1", "--timeout", "1"])
        expect_exit(rc, 4, out, err)
        check("slowest" not in out, f"summary printed before the run completed: {out}")
    finally:
        sb.close()


# ---------------------------------------------------------------------------
# ci_skip_check
# ---------------------------------------------------------------------------

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    proc = subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def commit_file(repo: Path, name: str, text: str, msg: str) -> str:
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def make_repo(root: Path) -> dict:
    """main: A, S (squash of PR head H, same tree as H), D (adds a file, different tree)."""
    repo = root / "work"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit_file(repo, "a.txt", "a\n", "A")
    git(repo, "checkout", "-q", "-b", "pr")
    head = commit_file(repo, "b.txt", "b\n", "H")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "--squash", "pr")
    git(repo, "commit", "-q", "-m", "S")
    squash = git(repo, "rev-parse", "HEAD")
    other = commit_file(repo, "c.txt", "c\n", "D")
    check(git(repo, "rev-parse", f"{squash}^{{tree}}") == git(repo, "rev-parse", f"{head}^{{tree}}"),
          "fixture repo: squash tree should equal PR head tree")
    check(git(repo, "rev-parse", f"{other}^{{tree}}") != git(repo, "rev-parse", f"{head}^{{tree}}"),
          "fixture repo: D tree should differ")
    return {"repo": repo, "squash": squash, "other": other, "head": head}


REPO = "o/r"
WF_REF = "o/r/.github/workflows/ci.yml@refs/heads/main"


def skip_fixture(sha: str, head: str, *, pulls="default", runs="default", jobs="default") -> dict:
    api = {}
    api[f"repos/{REPO}/commits/{sha}/pulls"] = (
        [{"number": 7, "merged_at": "2026-10-10T00:00:00Z", "head": {"sha": head}}]
        if pulls == "default" else pulls)
    api[f"repos/{REPO}/actions/runs?head_sha={head}&event=pull_request&status=success"] = (
        {"workflow_runs": [{"id": 100, "path": ".github/workflows/ci.yml",
                            "head_sha": head, "conclusion": "success"}]}
        if runs == "default" else runs)
    api[f"repos/{REPO}/actions/runs/100/jobs?per_page=100"] = (
        {"jobs": [{"conclusion": "skipped"}, {"conclusion": "success"}]}
        if jobs == "default" else jobs)
    return {"api": api}


def skip_run(sb: Sandbox, repo: Path, sha: str, fx: dict, *, output=True, env_extra=None):
    sb.write_fixture(fx)
    out_file = sb.dir / "github_output"
    out_file.write_text("", encoding="utf-8")
    env = {"GITHUB_SHA": sha, "GITHUB_REPOSITORY": REPO, "GITHUB_WORKFLOW_REF": WF_REF}
    if output:
        env["GITHUB_OUTPUT"] = str(out_file)
    env.update(env_extra or {})
    rc, out, err = sb.run(CI_SKIP, [], env_extra=env, cwd=repo)
    parsed = {}
    for line in out_file.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            parsed[k] = v
    return rc, out, err, parsed


@test
def skip_true_when_trees_match_and_pr_run_passed():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"], skip_fixture(r["squash"], r["head"]))
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "true", f"expected skip=true, got {o}\n{out}\n{err}")
        check(o.get("reason"), "skip=true without a reason")
    finally:
        sb.close()


@test
def skip_false_when_trees_differ():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        # Same passing PR run, but the pushed commit changed something more.
        rc, out, err, o = skip_run(sb, r["repo"], r["other"], skip_fixture(r["other"], r["head"]))
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false", f"expected skip=false, got {o}")
        check("differs" in o.get("reason", ""), f"reason should say the trees differ: {o}")
    finally:
        sb.close()


@test
def skip_false_when_no_pull_request():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"],
                                   skip_fixture(r["squash"], r["head"], pulls=[]))
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false" and "no pull request" in o.get("reason", ""), f"{o}")
    finally:
        sb.close()


@test
def skip_false_when_pr_run_did_not_succeed():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        # `status=success` returns nothing when the run failed.
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"],
                                   skip_fixture(r["squash"], r["head"], runs={"workflow_runs": []}))
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false", f"{o}")
    finally:
        sb.close()


@test
def skip_false_when_only_another_workflow_passed():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        other_wf = {"workflow_runs": [{"id": 100, "path": ".github/workflows/lint.yml",
                                       "head_sha": r["head"], "conclusion": "success"}]}
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"],
                                   skip_fixture(r["squash"], r["head"], runs=other_wf))
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false", f"{o}")
        # Contrast: path with the @ref suffix some events report still matches.
        suffixed = {"workflow_runs": [{"id": 100, "path": ".github/workflows/ci.yml@refs/pull/7/merge",
                                       "head_sha": r["head"], "conclusion": "success"}]}
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"],
                                   skip_fixture(r["squash"], r["head"], runs=suffixed))
        check(o.get("skip") == "true", f"a path with an @ref suffix should match: {o}")
    finally:
        sb.close()


@test
def skip_false_when_the_passing_run_ran_no_job():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        # A draft pull request's run has every job skipped and still reports success.
        draft = {"jobs": [{"conclusion": "skipped"}, {"conclusion": "skipped"}]}
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"],
                                   skip_fixture(r["squash"], r["head"], jobs=draft))
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false", f"all-skipped run must not count as tested: {o}")
        failed = {"jobs": [{"conclusion": "success"}, {"conclusion": "failure"}]}
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"],
                                   skip_fixture(r["squash"], r["head"], jobs=failed))
        check(o.get("skip") == "false", f"a run with a failed job must not count: {o}")
    finally:
        sb.close()


@test
def skip_false_when_gh_errors():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        fx = skip_fixture(r["squash"], r["head"], pulls={"__error": "HTTP 403: rate limited"})
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"], fx)
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false" and "403" in o.get("reason", ""), f"{o}")
        # gh failing on the runs call, after the PR was found, also fails open.
        fx = skip_fixture(r["squash"], r["head"], runs={"__error": "HTTP 500"})
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"], fx)
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false", f"{o}")
    finally:
        sb.close()


@test
def skip_false_when_environment_is_incomplete():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"], skip_fixture(r["squash"], r["head"]),
                                   env_extra={"GITHUB_WORKFLOW_REF": ""})
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "false" and "GITHUB_WORKFLOW_REF" in o.get("reason", ""), f"{o}")
        # A workflow ref from another repository cannot be trusted either.
        rc, out, err, o = skip_run(sb, r["repo"], r["squash"], skip_fixture(r["squash"], r["head"]),
                                   env_extra={"GITHUB_WORKFLOW_REF": "x/y/.github/workflows/ci.yml@refs/heads/main"})
        check(o.get("skip") == "false", f"{o}")
    finally:
        sb.close()


@test
def skip_prints_when_github_output_is_unset_and_appends_when_set():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        fx = skip_fixture(r["squash"], r["head"])
        rc, out, err, _ = skip_run(sb, r["repo"], r["squash"], fx, output=False)
        expect_exit(rc, 0, out, err)
        check("skip=true" in out, f"result should be printed when GITHUB_OUTPUT is unset: {out}")
        out_file = sb.dir / "github_output"
        out_file.write_text("earlier=1\n", encoding="utf-8")
        env = {"GITHUB_SHA": r["squash"], "GITHUB_REPOSITORY": REPO,
               "GITHUB_WORKFLOW_REF": WF_REF, "GITHUB_OUTPUT": str(out_file)}
        rc, out, err = sb.run(CI_SKIP, [], env_extra=env, cwd=r["repo"])
        text = out_file.read_text(encoding="utf-8")
        check(text.startswith("earlier=1\n") and "skip=true\n" in text and "reason=" in text,
              f"GITHUB_OUTPUT must be appended to, not overwritten: {text!r}")
    finally:
        sb.close()


@test
def skip_fetches_a_head_commit_that_is_missing_locally():
    sb = Sandbox()
    try:
        r = make_repo(sb.dir)
        repo = r["repo"]
        origin = sb.dir / "origin.git"
        git(sb.dir, "init", "-q", "--bare", str(origin))
        git(repo, "remote", "add", "origin", str(origin))
        git(repo, "push", "-q", "origin", "pr")
        git(repo, "branch", "-q", "-D", "pr")
        git(repo, "update-ref", "-d", "refs/remotes/origin/pr")
        git(repo, "reflog", "expire", "--expire=now", "--all")
        git(repo, "gc", "-q", "--prune=now")
        gone = subprocess.run(["git", "cat-file", "-e", f"{r['head']}^{{commit}}"], cwd=repo,
                              capture_output=True).returncode != 0
        check(gone, "fixture: the PR head should be absent locally")
        rc, out, err, o = skip_run(sb, repo, r["squash"], skip_fixture(r["squash"], r["head"]))
        expect_exit(rc, 0, out, err)
        check(o.get("skip") == "true", f"head should have been fetched from origin: {o} {out}")
        # Contrast: with no origin to fetch from the same situation fails open.
        git(repo, "remote", "remove", "origin")
        git(repo, "reflog", "expire", "--expire=now", "--all")
        git(repo, "gc", "-q", "--prune=now")
        rc, out, err, o = skip_run(sb, repo, r["squash"], skip_fixture(r["squash"], r["head"]))
        check(o.get("skip") == "false", f"unfetchable head must not skip: {o}")
    finally:
        sb.close()


# ---------------------------------------------------------------------------
# ci_skip_check: a merge that differs only in push paths-ignore paths (DS39)
# ---------------------------------------------------------------------------

WORKFLOW_BLOCK = """name: CI
on:
  pull_request:
    types: [opened]
    paths-ignore:
      - 'pr-only/**'
  push:
    branches: [main]
    paths-ignore:
      - 'apps/ios/**'   # a comment
      - '**/*.md'
      - "docs/**"
      - assets/*.png
concurrency:
  group: x
"""

WORKFLOW_FLOW = WORKFLOW_BLOCK.replace(
    "    paths-ignore:\n      - 'apps/ios/**'   # a comment\n      - '**/*.md'\n"
    "      - \"docs/**\"\n      - assets/*.png\n",
    "    paths-ignore: ['apps/ios/**', '**/*.md', \"docs/**\", assets/*.png]\n")


def import_skip_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_skip_check_under_test", CI_SKIP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_merge_repo(root: Path, *, workflow: str | None, extra: dict[str, str],
                    gate: str | None = None) -> dict:
    """main: A (workflow, optional gate.json), then the PR head H (b.txt) squashed as S
    (same tree as H), then D, which writes `extra`. The PR head's run passed."""
    repo = root / "work"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    if workflow is not None:
        (repo / ".github/workflows/ci.yml").write_text(workflow, encoding="utf-8")
    if gate is not None:
        (repo / "scripts/delivery").mkdir(parents=True)
        (repo / "scripts/delivery/gate.json").write_text(gate, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A")
    git(repo, "checkout", "-q", "-b", "pr")
    head = commit_file(repo, "b.txt", "b\n", "H")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "--squash", "pr")
    git(repo, "commit", "-q", "-m", "S")
    for name, text in extra.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "D")
    return {"repo": repo, "head": head, "sha": git(repo, "rev-parse", "HEAD")}


def skip_for_extra(workflow: str | None, extra: dict[str, str], gate: str | None = None) -> dict:
    sb = Sandbox()
    try:
        r = make_merge_repo(sb.dir, workflow=workflow, extra=extra, gate=gate)
        rc, out, err, o = skip_run(sb, r["repo"], r["sha"], skip_fixture(r["sha"], r["head"]))
        expect_exit(rc, 0, out, err)
        return o
    finally:
        sb.close()


@test
def skip_true_when_only_docs_differ():
    o = skip_for_extra(WORKFLOW_BLOCK, {"docs/x/new.txt": "d\n"})
    check(o.get("skip") == "true", f"{o}")
    reason = o.get("reason", "")
    check("#7" in reason and "docs/x/new.txt" in reason, f"reason should name the PR and the paths: {reason}")


@test
def skip_true_when_only_markdown_differs_anywhere():
    for path in ("README.md", "deep/er/NOTES.md"):
        o = skip_for_extra(WORKFLOW_BLOCK, {path: "m\n"})
        check(o.get("skip") == "true", f"{path}: {o}")
    # Contrast: a file that only looks like it (`.md` as a directory, `.mdx`) runs the suite.
    for path in ("notes.mdx", "x.md/real.txt"):
        o = skip_for_extra(WORKFLOW_BLOCK, {path: "m\n"})
        check(o.get("skip") == "false", f"{path}: {o}")


@test
def skip_true_when_only_an_ignored_mobile_folder_differs():
    o = skip_for_extra(WORKFLOW_BLOCK, {"apps/ios/App/Info.plist": "p\n", "docs/a.txt": "d\n"})
    check(o.get("skip") == "true", f"{o}")
    # `*` stops at `/`: assets/*.png ignores assets/a.png but not assets/sub/a.png.
    check(skip_for_extra(WORKFLOW_BLOCK, {"assets/a.png": "x\n"}).get("skip") == "true", "assets/a.png")
    check(skip_for_extra(WORKFLOW_BLOCK, {"assets/sub/a.png": "x\n"}).get("skip") == "false", "assets/sub/a.png")


@test
def skip_false_when_any_other_file_differs():
    o = skip_for_extra(WORKFLOW_BLOCK, {"docs/ok.md": "d\n", "src/main.ts": "x\n"})
    check(o.get("skip") == "false", f"{o}")
    check("src/main.ts" in o.get("reason", ""), f"reason should name the live path: {o}")
    # A path ignored only for pull requests is not ignored for push.
    check(skip_for_extra(WORKFLOW_BLOCK, {"pr-only/a.txt": "x\n"}).get("skip") == "false", "pr-only")
    # An ignored folder one level too deep or too shallow does not match.
    check(skip_for_extra(WORKFLOW_BLOCK, {"other/docs/a.txt": "x\n"}).get("skip") == "false", "other/docs")


@test
def skip_reads_the_one_line_paths_ignore_form_too():
    check(skip_for_extra(WORKFLOW_FLOW, {"docs/a.txt": "d\n"}).get("skip") == "true", "flow form")
    check(skip_for_extra(WORKFLOW_FLOW, {"src/a.txt": "d\n"}).get("skip") == "false", "flow form, live path")


@test
def skip_false_when_the_workflow_has_no_push_paths_ignore():
    no_list = WORKFLOW_BLOCK.replace(
        "    paths-ignore:\n      - 'apps/ios/**'   # a comment\n      - '**/*.md'\n"
        "      - \"docs/**\"\n      - assets/*.png\n", "")
    check(no_list != WORKFLOW_BLOCK, "fixture should have lost the push list")
    o = skip_for_extra(no_list, {"docs/a.txt": "d\n"})
    check(o.get("skip") == "false" and "paths-ignore" in o.get("reason", ""), f"{o}")
    # ... no push trigger at all, and no workflow file in the commit.
    o = skip_for_extra("name: CI\non:\n  pull_request:\n    types: [opened]\n", {"docs/a.txt": "d\n"})
    check(o.get("skip") == "false", f"{o}")
    check(skip_for_extra(None, {"docs/a.txt": "d\n"}).get("skip") == "false", "no workflow file")


@test
def skip_false_when_the_list_cannot_be_parsed():
    for label, text in (
        ("an anchor", WORKFLOW_BLOCK.replace("      - '**/*.md'", "      - *md")),
        ("a nested list", WORKFLOW_BLOCK.replace("      - '**/*.md'", "      - ['**/*.md']")),
        ("an unquoted flow list", WORKFLOW_BLOCK.replace(
            "    paths-ignore:\n      - 'apps/ios/**'", "    paths-ignore: *shared\n      - 'apps/ios/**'")),
        ("a character class", WORKFLOW_BLOCK.replace("'**/*.md'", "'docs/[a-z]*'")),
        ("no on block", "name: CI\njobs: {}\n"),
    ):
        o = skip_for_extra(text, {"docs/a.txt": "d\n"})
        check(o.get("skip") == "false", f"{label}: expected skip=false, got {o}")


@test
def skip_ci_skip_paths_in_gate_json_replaces_the_workflow_list():
    gate = json.dumps({"ci_skip_paths": ["generated/**"]})
    # docs/** is in the workflow list but the override replaces it ...
    check(skip_for_extra(WORKFLOW_BLOCK, {"docs/a.txt": "d\n"}, gate).get("skip") == "false", "override replaces")
    # ... and the override alone decides, even for a workflow without any list.
    o = skip_for_extra("name: CI\non:\n  push:\n    branches: [main]\n", {"generated/a.ts": "g\n"}, gate)
    check(o.get("skip") == "true", f"{o}")
    # An unusable override is not guessed around.
    check(skip_for_extra(WORKFLOW_BLOCK, {"docs/a.txt": "d\n"}, '{"ci_skip_paths": "docs/**"}').get("skip") == "false",
          "string override")
    check(skip_for_extra(WORKFLOW_BLOCK, {"docs/a.txt": "d\n"}, "{not json").get("skip") == "false", "bad gate.json")
    # A gate.json without the key leaves the workflow list in charge.
    check(skip_for_extra(WORKFLOW_BLOCK, {"docs/a.txt": "d\n"}, "{}").get("skip") == "true", "no key")


@test
def skip_ignored_paths_still_need_a_passed_run():
    sb = Sandbox()
    try:
        r = make_merge_repo(sb.dir, workflow=WORKFLOW_BLOCK, extra={"docs/a.txt": "d\n"})
        rc, out, err, o = skip_run(sb, r["repo"], r["sha"],
                                   skip_fixture(r["sha"], r["head"], runs={"workflow_runs": []}))
        check(o.get("skip") == "false", f"a docs-only diff must not skip without a passed run: {o}")
    finally:
        sb.close()


@test
def every_track_ci_skips_docs_and_markdown_on_push():
    mod = import_skip_module()
    for track in TRACKS:
        text = read(TOOLING / track / ".github/workflows/ci.yml")
        listed = mod.push_paths_ignore(text)
        check(listed and "docs/**" in listed and "**/*.md" in listed,
              f"{track}: push paths-ignore must list docs/** and **/*.md, got {listed}")
        for pattern in listed:
            mod.glob_regex(pattern)  # every shipped pattern is one the skip check understands
        check(mod.glob_regex("docs/**").fullmatch("docs/a/b.txt") and mod.glob_regex("**/*.md").fullmatch("a/b.md")
              and mod.glob_regex("**/*.md").fullmatch("b.md") and not mod.glob_regex("docs/**").fullmatch("docsx/a"),
              "glob semantics")


@test
def skip_check_detects_each_defect():
    """The tests above can fail: break ci_skip_check.py in each way and expect one to notice."""
    global CI_SKIP
    original = CI_SKIP.read_text(encoding="utf-8").replace("\r\n", "\n")
    cases = [
        ("every changed path is no longer required to match",
         "    live = [p for p in changed if not any(r.fullmatch(p) for r in regexes)]",
         "    live = [p for p in changed if not any(r.fullmatch(p) for r in regexes)][:0]"),
        ("`**` stops crossing `/`", '            out += ".*"\n', '            out += "[^/]*"\n'),
        ("`*` crosses `/`", '            out += "[^/]*"\n            i += 1', '            out += ".*"\n            i += 1'),
        ("a prefix match instead of a full match", "r.fullmatch(p) for r in regexes", "r.match(p) for r in regexes"),
        ("the override ignored", "            return override\n", "            pass\n"),
        ("the pull_request list read as the push list",
         '    push_at = next((k for k, ln in enumerate(block) if re.fullmatch(r"  push:\\s*(#.*)?", ln)), None)',
         '    push_at = next((k for k, ln in enumerate(block) if re.fullmatch(r"  pull_request:\\s*(#.*)?", ln)), None)'),
        ("an unsupported glob accepted", 'if re.search(r"[?\\[\\]+!]", pattern):', "if False:"),
        ("no list means skip", '        raise Undecided(f"{wf_path} has no push paths-ignore list")', "        return ['**']"),
    ]
    detect = [skip_true_when_only_docs_differ, skip_true_when_only_markdown_differs_anywhere,
              skip_true_when_only_an_ignored_mobile_folder_differs, skip_false_when_any_other_file_differs,
              skip_reads_the_one_line_paths_ignore_form_too, skip_false_when_the_workflow_has_no_push_paths_ignore,
              skip_false_when_the_list_cannot_be_parsed, skip_ci_skip_paths_in_gate_json_replaces_the_workflow_list]
    saved = CI_SKIP
    with tempfile.TemporaryDirectory(prefix="ds39-") as d:
        for label, old, new in cases:
            mutated = mutate(original, old, new)
            path = Path(d) / "ci_skip_check.py"
            path.write_text(mutated, encoding="utf-8", newline="\n")
            CI_SKIP = path
            try:
                caught = False
                for fn in detect:
                    try:
                        fn()
                    except Exception:  # noqa: BLE001 - any failing test is a detection
                        caught = True
                        break
                check(caught, f"mutation '{label}' was not detected by any skip test")
            finally:
                CI_SKIP = saved


# ---------------------------------------------------------------------------
# reach_check
# ---------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    seen_agents: list = []

    def do_GET(self):  # noqa: N802
        _Handler.seen_agents.append(self.headers.get("User-Agent", ""))
        if self.path == "/ok":
            self.send_response(200)
        elif self.path == "/boom":
            self.send_response(500)
        elif self.path == "/missing":
            self.send_response(404)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
        else:
            self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):  # silence
        pass


def serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def reach(urls: list[str], extra: list[str] | None = None):
    env = {**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
           "PYTHONUTF8": "1"}
    for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    proc = subprocess.run([sys.executable, "-I", str(REACH), *urls, *(extra or ["--timeout", "5"])],
                          env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


@test
def reach_200_is_exit_0_and_500_is_exit_1():
    srv, base = serve()
    try:
        rc, out, err = reach([base + "/ok"])
        expect_exit(rc, 0, out, err)
        check("200" in out and base + "/ok" in out, f"table should show url and status: {out}")
        rc, out, err = reach([base + "/boom"])
        expect_exit(rc, 1, out, err)
        check("500" in out, f"{out}")
    finally:
        srv.shutdown()


@test
def reach_4xx_counts_as_reachable():
    srv, base = serve()
    try:
        rc, out, err = reach([base + "/missing"])
        expect_exit(rc, 0, out, err)
        check("404" in out, out)
    finally:
        srv.shutdown()


@test
def reach_follows_redirects_and_sends_a_normal_user_agent():
    srv, base = serve()
    try:
        _Handler.seen_agents.clear()
        rc, out, err = reach([base + "/redirect"])
        expect_exit(rc, 0, out, err)
        check("200" in out, f"redirect should be followed to the 200: {out}")
        check(_Handler.seen_agents and all("urllib" not in a and a.startswith("Mozilla/")
                                           for a in _Handler.seen_agents),
              f"expected a normal User-Agent, got {_Handler.seen_agents}")
    finally:
        srv.shutdown()


@test
def reach_connection_refused_is_exit_1():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    rc, out, err = reach([f"http://127.0.0.1:{port}/"])
    expect_exit(rc, 1, out, err)
    check("FAIL" in out and "error" in out, f"error should be in the table: {out}")


@test
def reach_one_bad_url_fails_the_run_and_all_are_listed():
    srv, base = serve()
    try:
        rc, out, err = reach([base + "/ok", base + "/boom"])
        expect_exit(rc, 1, out, err)
        check(base + "/ok" in out and base + "/boom" in out, f"every URL should be listed: {out}")
    finally:
        srv.shutdown()


@test
def reach_rejects_non_http_urls():
    rc, out, err = reach(["file:///etc/passwd"])
    expect_exit(rc, 2, out, err)


# ---------------------------------------------------------------------------
# Structural checks of the four ci.yml files
# ---------------------------------------------------------------------------

IF_COND = ("${{ !cancelled() && needs.decide.outputs.skip != 'true' && "
           "(github.event_name != 'pull_request' || !github.event.pull_request.draft) }}")

# The ts runner plan (DS9) adds one clause to the jobs it can skip: a planned skip is an explicit 'false'.
PLAN_CLAUSE = re.compile(r" && needs\.plan\.outputs\.(integration|e2e) != 'false'")


def if_cond_ok(block: str) -> bool:
    for m in re.finditer(r"^    if: (.*)$", block, re.M):
        if m.group(1) == IF_COND or PLAN_CLAUSE.sub("", m.group(1)) == IF_COND:
            return True
    return False


REQUIRED_NAMES = {
    "ts": ["lint, types, boundaries, unit + contract tests",
           "integration tests (ephemeral Postgres)", "web E2E (§11.2)"],
    "go": ["lint, vet, boundaries, unit + contract tests",
           "integration tests (ephemeral database)"],
    "rust": ["clippy, fmt, build, unit + contract tests",
             "integration tests (ephemeral database)"],
    "dotnet": ["analyzers, format, build, unit + contract tests",
               "integration tests (ephemeral database)"],
}


RUNS_ON = "runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '\"ubuntu-latest\"') }}"

CONCURRENCY = (
    "concurrency:\n"
    "  # Outdated PR runs are cancelled. Runs on main never are: every commit on main\n"
    "  # must finish its run, because cancelling one can leave a merged commit\n"
    "  # unverified. With the repository variable CI_SERIAL=true (self-hosted or\n"
    "  # shared runners) ready-PR runs queue one at a time and are never cancelled.\n"
    "  group: ${{ vars.CI_SERIAL == 'true' && github.event_name == 'pull_request' && 'ci-ready-serial' "
    "|| format('ci-{0}', github.ref) }}\n"
    "  cancel-in-progress: ${{ github.event_name == 'pull_request' && vars.CI_SERIAL != 'true' }}\n"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def split_jobs(text: str) -> dict[str, str]:
    start = text.find("\njobs:\n")
    if start < 0:
        return {}
    body = text[start + len("\njobs:\n"):]
    marks = list(re.finditer(r"^  ([A-Za-z0-9_-]+):[ \t]*$", body, re.M))
    jobs = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        jobs[m.group(1)] = body[m.start():end]
    return jobs


def split_steps(block: str) -> list[str]:
    parts = re.split(r"^(?=      - )", block, flags=re.M)
    return [p for p in parts[1:]]


def check_workflow(track: str, text: str) -> list[str]:
    """Return the problems found in one ci.yml (empty when it conforms)."""
    problems: list[str] = []
    jobs = split_jobs(text)
    if not jobs:
        return ["no jobs found"]

    # decide
    if list(jobs)[0] != "decide":
        problems.append("decide must be the first job")
    d = jobs.get("decide")
    if d is None:
        problems.append("decide job missing")
    else:
        if not re.search(r"^    name: ['\"]?decide: skip a tree already tested['\"]?\s*$", d, re.M):
            problems.append("decide job name is not 'decide: skip a tree already tested'")
        if not re.search(r"^    if: \$\{\{ github\.event_name == 'push' \}\}\s*$", d, re.M):
            problems.append("decide must run only on push")
        if not re.search(r"^          fetch-depth: 0\s*$", d, re.M):
            problems.append("decide checkout must use fetch-depth: 0")
        if "python3 scripts/delivery/ci_skip_check.py" not in d:
            problems.append("decide must run scripts/delivery/ci_skip_check.py")
        if "GH_TOKEN: ${{ github.token }}" not in d:
            problems.append("decide needs GH_TOKEN: ${{ github.token }}")
        for perm in ("contents: read", "pull-requests: read", "actions: read"):
            if not re.search(rf"^      {re.escape(perm)}\s*$", d, re.M):
                problems.append(f"decide permissions lack {perm}")
        if not re.search(r"^      skip: \$\{\{ steps\.\w+\.outputs\.skip \}\}\s*$", d, re.M):
            problems.append("decide must output skip")

    # every other job
    for name, block in jobs.items():
        if name == "decide":
            continue
        if not re.search(r"^    needs: (decide|\[decide(, [\w-]+)+\])\s*$", block, re.M):
            problems.append(f"job {name}: missing 'needs: decide'")
        if not if_cond_ok(block):
            problems.append(f"job {name}: missing the exact decide-aware 'if:' condition")
    for name, block in jobs.items():
        if re.search(r"^    continue-on-error:", block, re.M):
            problems.append(f"job {name}: job-level continue-on-error")

    # required check names stay as they are
    for want in REQUIRED_NAMES[track]:
        if not re.search(rf"^    name: {re.escape(want)}\s*$", text, re.M):
            problems.append(f"job name {want!r} missing or changed")

    # secret scan: pinned, full history
    v = jobs.get("verify", "")
    if "gitleaks/gitleaks-action" in text:
        problems.append("unpinned gitleaks-action still used")
    if "scripts/delivery/tools.json" not in v or "gitleaks" not in v:
        problems.append("verify must install gitleaks from scripts/delivery/tools.json")
    if not re.search(r"^          fetch-depth: 0\s*$", v, re.M):
        problems.append("verify checkout must use fetch-depth: 0 (gitleaks scans full history)")
    if "sha256sum -c" not in v:
        problems.append("gitleaks download is not checksum verified")
    if "['sha256']['linux_x64']" not in v:
        problems.append("gitleaks is not checked against the SHA-256 pinned in tools.json")
    elif 'echo "${sha}  ${archive}" | sha256sum -c -' not in v:
        problems.append("the pinned SHA-256 is not what the archive is checked against")
    if "::warning::" not in v or "old form" not in v:
        problems.append("the old tools.json form must be read with a warning")
    if v.count("checksums.txt") != 2:
        problems.append("the release's checksums file must only be the fallback for the old form")

    # triggers, paths-ignore, concurrency kept
    if text.count("docs/**") < 2:
        problems.append("docs/** must stay in paths-ignore for pull_request and push")
    if "\n" + CONCURRENCY not in text:
        problems.append("concurrency block differs from CONTRACT U8 (one ready-PR run at a time)")
    if "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in text:
        problems.append("concurrency must cancel only pull-request runs, and not under CI_SERIAL")
    problems += runs_on_problems(text)
    if "branches: [main]" not in text or "ready_for_review" not in text:
        problems.append("push/pull_request triggers changed")

    if track == "ts":
        problems += check_ts_e2e(text, jobs)
    return problems


def runs_on_problems(text: str) -> list[str]:
    """Every job takes its runner from the CI_RUNS_ON variable (U5)."""
    lines = re.findall(r"^\s*runs-on:.*$", text, re.M)
    if not lines:
        return ["no runs-on found"]
    return [f"runs-on is not the CI_RUNS_ON expression: {ln.strip()}"
            for ln in lines if ln.strip() != RUNS_ON]


def jobs_of(text: str) -> dict[str, str]:
    return split_jobs(text)


def check_ts_e2e(text: str, jobs: dict[str, str]) -> list[str]:
    problems = []
    e = jobs.get("e2e")
    sh = jobs.get("e2e-shard")
    if e is None:
        return ["ts: e2e job missing"]
    if sh is None:
        return ["ts: e2e-shard job missing (the browser suite must run as shards)"]
    if not re.search(r"^    name: web E2E \(§11\.2\)\s*$", e, re.M):
        problems.append("ts: e2e job must be named 'web E2E (§11.2)'")
    if not re.search(r"^    needs: \[decide, plan, e2e-shard\]\s*$", e, re.M):
        problems.append("ts: e2e (the required check) must need e2e-shard")
    for name, block in (("e2e", e), ("e2e-shard", sh)):
        if re.search(r"^    continue-on-error:", block, re.M):
            problems.append(f"ts: {name} must not be continue-on-error at job level")
        if "advisory" in block.lower():
            problems.append(f"ts: {name} is still described as advisory")
    if not re.search(r"^      fail-fast: false\s*$", sh, re.M):
        problems.append("ts: e2e-shard needs fail-fast: false")
    if not re.search(r"^        shard: \[1, 2\]\s*$", sh, re.M):
        problems.append("ts: e2e-shard must set the shard list in one place, default 2 shards")
    plan = jobs_of(text).get("plan")
    if plan is None:
        problems.append("ts: the runner plan job is missing")
    else:
        if not re.search(r"^    name: ['\"]?runner plan: ", plan, re.M):
            problems.append("ts: the plan job must be named 'runner plan: ...'")
        if "python3 scripts/delivery/area_select.py --base" not in plan:
            problems.append("ts: the runner plan must run area_select.py")
    for name, block in (("integration", jobs_of(text).get("integration", "")), ("e2e-shard", sh)):
        want = "integration" if name == "integration" else "e2e"
        if f"needs.plan.outputs.{want} != 'false'" not in block:
            problems.append(f"ts: {name} must skip only on an explicit 'false' from the runner plan")
    if 'if [ "$PLANNED" = "false" ]' not in e:
        problems.append("ts: the e2e summary must accept a planned skip")
    steps = split_steps(sh)
    quarantine = [s for s in steps if "E2E_QUARANTINE: only" in s]
    gating = [s for s in steps if "playwright test" in s and "E2E_QUARANTINE" not in s]
    if len(quarantine) != 1:
        problems.append("ts: e2e needs exactly one step running with E2E_QUARANTINE: only")
    elif not re.search(r"^        continue-on-error: true\s*$", quarantine[0], re.M):
        problems.append("ts: the quarantine step must be continue-on-error: true")
    if len(gating) != 1:
        problems.append("ts: e2e needs exactly one gating playwright step")
    elif "continue-on-error" in gating[0]:
        problems.append("ts: the gating E2E step must not be continue-on-error")
    balance = [s for s in steps if "id: balance" in s]
    if len(balance) != 1 or "shard_balance.py" not in balance[0]:
        problems.append("ts: e2e-shard needs one balance step running shard_balance.py")
    elif 'echo "args=--shard=${{ matrix.shard }}/${{ strategy.job-total }}" >> "$GITHUB_OUTPUT"' not in balance[0]:
        problems.append("ts: the balance step does not fall back to --shard")
    for s in gating + quarantine:
        if "${{ steps.balance.outputs.args }}" not in s:
            problems.append("ts: a playwright step does not pass --shard")
    if '[ "$SHARDS" = "success" ]' not in e:
        problems.append("ts: the e2e summary must fail unless every shard succeeded")
    return problems


def mutate(text: str, old: str, new: str, count: int = 1) -> str:
    check(old in text, f"mutation target not found: {old!r}")
    return text.replace(old, new, count)


@test
def workflows_conform():
    for track in TRACKS:
        path = TOOLING / track / ".github/workflows/ci.yml"
        problems = check_workflow(track, read(path))
        check(not problems, f"{track}/ci.yml:\n  " + "\n  ".join(problems))


@test
def shared_workflows_take_their_runner_from_the_variable():
    for name in SHARED_WORKFLOWS:
        text = read(TOOLING / "shared/.github/workflows" / name)
        check(not runs_on_problems(text), f"{name}: {runs_on_problems(text)}")
        check(runs_on_problems(text.replace(RUNS_ON, "runs-on: ubuntu-latest")),
              f"{name}: a hard-coded runner was not detected")


@test
def workflow_checker_detects_each_defect():
    ts = read(TOOLING / "ts/.github/workflows/ci.yml")
    go = read(TOOLING / "go/.github/workflows/ci.yml")
    cond_line = f"    if: {IF_COND}\n"
    cases = [
        ("ts", ts, "missing 'needs: decide'", lambda t: mutate(t, "    needs: decide\n", "", 3)),
        ("go", go, "missing 'needs: decide'",
         lambda t: mutate(t, "    needs: decide\n", "", 1)),
        ("ts", ts, "exact decide-aware", lambda t: mutate(t, "!cancelled() && ", "")),
        ("ts", ts, "exact decide-aware",
         lambda t: mutate(t, "needs.decide.outputs.skip != 'true' && ", "")),
        ("go", go, "exact decide-aware",
         lambda t: mutate(t, cond_line, "    if: ${{ !github.event.pull_request.draft }}\n", 1)),
        ("ts", ts, "decide job name", lambda t: mutate(t, "decide: skip a tree already tested", "decide")),
        ("ts", ts, "decide job missing", lambda t: mutate(t, "  decide:\n", "  decidex:\n")),
        ("ts", ts, "decide must run only on push",
         lambda t: mutate(t, "if: ${{ github.event_name == 'push' }}", "if: ${{ true }}")),
        ("go", go, "decide checkout must use fetch-depth",
         lambda t: mutate(t, "          # The pull-request head commit must be present to compare trees.\n"
                             "          fetch-depth: 0\n", "")),
        ("rust", read(TOOLING / "rust/.github/workflows/ci.yml"), "decide permissions lack actions: read",
         lambda t: mutate(t, "      actions: read\n", "")),
        ("dotnet", read(TOOLING / "dotnet/.github/workflows/ci.yml"), "GH_TOKEN",
         lambda t: mutate(t, "GH_TOKEN: ${{ github.token }}", "GH_TOKEN: x")),
        ("ts", ts, "verify checkout must use fetch-depth: 0",
         lambda t: mutate(t, "          fetch-depth: 0\n\n      # §12: secret scanning",
                          "\n      # §12: secret scanning")),
        ("go", go, "unpinned gitleaks-action",
         lambda t: t + "\n      - uses: gitleaks/gitleaks-action@v2\n"),
        ("ts", ts, "tools.json", lambda t: mutate(t, "scripts/delivery/tools.json", "tools.json", 10)),
        ("ts", ts, "docs/**", lambda t: mutate(t, "      - 'docs/**'\n", "", 2)),
        ("go", go, "docs/**", lambda t: mutate(t, "'docs/**'", "'doc/**'", 2)),
        ("ts", ts, "concurrency block differs",
         lambda t: mutate(t, "cancel-in-progress: ${{ github.event_name == 'pull_request' && vars.CI_SERIAL != 'true' }}",
                          "cancel-in-progress: true")),
        ("go", go, "concurrency block differs",
         lambda t: mutate(t, "'ci-ready-serial'", "'ci-serial'")),
        ("rust", read(TOOLING / "rust/.github/workflows/ci.yml"), "concurrency block differs",
         lambda t: mutate(t, "format('ci-{0}', github.ref)", "format('ci-{0}', github.workflow)")),
        ("dotnet", read(TOOLING / "dotnet/.github/workflows/ci.yml"), "concurrency must cancel only",
         lambda t: t.replace(CONCURRENCY, "concurrency:\n  group: ci-${{ github.ref }}\n"
                             "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n")),
        ("ts", ts, "runs-on is not the CI_RUNS_ON expression",
         lambda t: mutate(t, RUNS_ON, "runs-on: ubuntu-latest", 1)),
        ("go", go, "runs-on is not the CI_RUNS_ON expression",
         lambda t: mutate(t, RUNS_ON, "runs-on: ${{ vars.CI_RUNS_ON }}", 2)),
        ("rust", read(TOOLING / "rust/.github/workflows/ci.yml"), "runs-on is not the CI_RUNS_ON expression",
         lambda t: mutate(t, RUNS_ON, "runs-on: windows-latest", 3)),
        ("dotnet", read(TOOLING / "dotnet/.github/workflows/ci.yml"), "runs-on is not the CI_RUNS_ON expression",
         lambda t: mutate(t, RUNS_ON, "runs-on: ubuntu-24.04", 1)),
        ("ts", ts, "not checked against the SHA-256 pinned",
         lambda t: mutate(t, "g['sha256']['linux_x64']", "g['version']")),
        ("go", go, "pinned SHA-256 is not what the archive",
         lambda t: mutate(t, 'echo "${sha}  ${archive}" | sha256sum -c -', 'echo "${sha}  ${archive}"')),
        ("rust", read(TOOLING / "rust/.github/workflows/ci.yml"), "old tools.json form must be read with a warning",
         lambda t: mutate(t, "::warning::", "::notice::")),
        ("dotnet", read(TOOLING / "dotnet/.github/workflows/ci.yml"), "only be the fallback",
         lambda t: mutate(t, "          fi\n          tar -xzf",
                          "          fi\n          curl -sSfL -O \"${base}/gitleaks_${version}_checksums.txt\"\n          tar -xzf")),
        ("ts", ts, "job name",
         lambda t: mutate(t, "name: integration tests (ephemeral Postgres)", "name: integration")),
        ("ts", ts, "named 'web E2E",
         lambda t: mutate(t, "name: web E2E (§11.2)", "name: web E2E (advisory, §11.2)")),
        ("ts", ts, "job-level continue-on-error",
         lambda t: mutate(t, "    name: web E2E (§11.2)\n",
                          "    name: web E2E (§11.2)\n    continue-on-error: true\n")),
        ("ts", ts, "quarantine step must be continue-on-error",
         lambda t: mutate(t, "        continue-on-error: true\n        env:\n          E2E_QUARANTINE",
                          "        env:\n          E2E_QUARANTINE")),
        ("ts", ts, "gating E2E step must not be continue-on-error",
         lambda t: mutate(t, "        run: pnpm exec playwright test ${{ steps.balance.outputs.args }}",
                          "        continue-on-error: true\n        run: pnpm exec playwright test ${{ steps.balance.outputs.args }}")),
        ("ts", ts, "e2e-shard needs fail-fast: false",
         lambda t: mutate(t, "fail-fast: false", "fail-fast: true")),
        ("ts", ts, "does not pass --shard",
         lambda t: mutate(t, "playwright test ${{ steps.balance.outputs.args }}", "playwright test")),
        ("ts", ts, "balance step does not fall back to --shard",
         lambda t: mutate(t, 'echo "args=--shard=${{ matrix.shard }}/${{ strategy.job-total }}"', 'echo "args="')),
        ("ts", ts, "needs one balance step",
         lambda t: mutate(t, "shard_balance.py --glob", "shard_balance_x.py --glob")),
        ("ts", ts, "must fail unless every shard succeeded",
         lambda t: mutate(t, '[ "$SHARDS" = "success" ]', "true")),
        ("ts", ts, "runner plan job is missing", lambda t: mutate(t, "  plan:\n", "  planx:\n")),
        ("ts", ts, "must run area_select.py", lambda t: mutate(t, "python3 scripts/delivery/area_select.py --base", "echo --base")),
        ("ts", ts, "integration must skip only on an explicit",
         lambda t: mutate(t, "needs.plan.outputs.integration != 'false'", "needs.plan.outputs.integration == 'true'")),
        ("ts", ts, "e2e-shard must skip only on an explicit",
         lambda t: mutate(t, "needs.plan.outputs.e2e != 'false'", "needs.plan.outputs.e2e == 'true'")),
        ("ts", ts, "must accept a planned skip", lambda t: mutate(t, 'if [ "$PLANNED" = "false" ]', 'if false')),
        ("ts", ts, "must need e2e-shard",
         lambda t: mutate(t, "needs: [decide, plan, e2e-shard]", "needs: decide")),
        ("ts", ts, "exactly one step running with E2E_QUARANTINE",
         lambda t: mutate(t, "E2E_QUARANTINE: only", "E2E_QUARANTINE: no")),
    ]
    for track, text, expect, fn in cases:
        check(not check_workflow(track, text), f"baseline {track} should conform before mutating")
        problems = check_workflow(track, fn(text))
        check(any(expect in p for p in problems),
              f"mutation expecting {expect!r} was not detected; got {problems}")


@test
def playwright_config_and_quarantine_file():
    cfg = read(TOOLING / "ts/playwright.config.ts")
    for needle in ("E2E_QUARANTINE", "testIgnore", "testMatch", "retries: 0", "quarantine.json"):
        check(needle in cfg, f"playwright.config.ts lacks {needle!r}")
    check(re.search(r"retries:\s*0", cfg) and not re.search(r"retries:\s*[1-9]", cfg),
          "gating specs must never be retried (11.3)")
    check("never retried" in cfg or "never re-run" in cfg or "never retried until green" in cfg,
          "retries: 0 should carry a comment citing 11.3")
    data = json.loads((TOOLING / "ts/e2e/quarantine.json").read_text(encoding="utf-8"))
    check(data == [], f"quarantine.json must ship as an empty list, got {data!r}")
    # The checker can fail: a config that retries is rejected by the same regex.
    bad = cfg.replace("retries: 0", "retries: 2")
    check(re.search(r"retries:\s*[1-9]", bad), "retry detector cannot fail")


@test
def tooling_readme_documents_the_new_flow():
    text = read(TOOLING / "README.md")
    problems = readme_problems(text)
    check(not problems, "README: " + "; ".join(problems))
    # Contrast: the old wording is caught.
    check(readme_problems(text + "\n- **E2E is advisory.** x\n"), "stale wording not detected")
    check(readme_problems(text.replace("ci_watch.py", "")), "missing ci_watch.py not detected")


def readme_problems(text: str) -> list[str]:
    out = []
    for needle in ("web E2E (§11.2)", "decide: skip a tree already tested", "quarantine.json",
                   "ci_watch.py", "reach_check.py", "ci_skip_check.py"):
        if needle not in text:
            out.append(f"missing {needle!r}")
    if "E2E is advisory" in text or "web E2E (advisory" in text:
        out.append("still calls E2E advisory")
    return out


# ---------------------------------------------------------------------------
# tools.json pins: tools_pin.py and agent_setup.sh
# ---------------------------------------------------------------------------

VERSION = "8.30.1"
PLATFORM_ASSETS = {
    "linux_x64": "linux_x64.tar.gz", "linux_arm64": "linux_arm64.tar.gz",
    "darwin_x64": "darwin_x64.tar.gz", "darwin_arm64": "darwin_arm64.tar.gz",
    "windows_x64": "windows_x64.zip",
}


def fake_checksums(version: str = VERSION, skip: str | None = None) -> tuple[str, dict[str, str]]:
    """A release checksums file (extra platforms included) and the digest per pin key."""
    digests, lines = {}, []
    for i, (key, suffix) in enumerate(PLATFORM_ASSETS.items(), start=1):
        digests[key] = f"{i:x}" * 64
        if key != skip:
            lines.append(f"{digests[key]}  gitleaks_{version}_{suffix}")
    lines.append("f" * 64 + f"  gitleaks_{version}_linux_armv7.tar.gz")
    return "\n".join(lines) + "\n", digests


def run_py(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONUTF8": "1", "NO_PROXY": "127.0.0.1,localhost"}
    return subprocess.run([sys.executable, "-I", *args], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


@test
def tools_pin_writes_the_five_digests_from_a_local_checksums_file():
    with tempfile.TemporaryDirectory(prefix="ds32-") as d:
        d = Path(d)
        text, digests = fake_checksums()
        (d / "sums.txt").write_text(text, encoding="utf-8")
        tools = d / "tools.json"
        tools.write_text('{"gitleaks": "8.0.0", "other": 1}\n', encoding="utf-8")
        r = run_py([str(TOOLS_PIN), "gitleaks", VERSION, "--checksums", str(d / "sums.txt"),
                    "--tools-json", str(tools)])
        expect_exit(r.returncode, 0, r.stdout, r.stderr)
        got = json.loads(tools.read_text(encoding="utf-8"))
        check(got["gitleaks"] == {"version": VERSION, "sha256": digests},
              f"unexpected tools.json: {got}")
        check(got["other"] == 1, "unrelated keys must be kept")
        check(tools.read_text(encoding="utf-8").endswith("\n"), "file should end with a newline")

        # Contrast: a platform missing from the file is exit 1 and tools.json stays as it was.
        text, _ = fake_checksums(skip="windows_x64")
        (d / "sums.txt").write_text(text, encoding="utf-8")
        before = tools.read_text(encoding="utf-8")
        r = run_py([str(TOOLS_PIN), "gitleaks", VERSION, "--checksums", str(d / "sums.txt"),
                    "--tools-json", str(tools)])
        expect_exit(r.returncode, 1, r.stdout, r.stderr)
        check("windows_x64" in r.stderr, r.stderr)
        check(tools.read_text(encoding="utf-8") == before, "tools.json must not change on failure")
        # ... and a version the file does not list is the same failure.
        r = run_py([str(TOOLS_PIN), "gitleaks", "9.9.9", "--checksums", str(d / "sums.txt"),
                    "--tools-json", str(tools)])
        expect_exit(r.returncode, 1, r.stdout, r.stderr)


@test
def tools_pin_usage_and_download_errors():
    r = run_py([str(TOOLS_PIN), "gitleaks", "latest"])
    expect_exit(r.returncode, 2, r.stdout, r.stderr)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="ds32-") as d:
        tools = Path(d) / "tools.json"
        r = run_py([str(TOOLS_PIN), "gitleaks", VERSION, "--base-url", f"http://127.0.0.1:{port}",
                    "--tools-json", str(tools)])
        expect_exit(r.returncode, 2, r.stdout, r.stderr)
        check(not tools.exists(), "nothing may be written when the download fails")
        r = run_py([str(TOOLS_PIN), "gitleaks", VERSION, "--checksums", str(Path(d) / "absent.txt"),
                    "--tools-json", str(tools)])
        expect_exit(r.returncode, 2, r.stdout, r.stderr)


class _Release(http.server.BaseHTTPRequestHandler):
    files: dict[str, bytes] = {}
    requests: list[str] = []

    def do_GET(self):  # noqa: N802
        name = self.path.lstrip("/")
        _Release.requests.append(name)
        body = _Release.files.get(name)
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Length", str(len(body or b"")))
        self.end_headers()
        self.wfile.write(body or b"")

    def log_message(self, *a):  # silence
        pass


def host_platform() -> tuple[str, str] | None:
    """(tools.json key, executable name) for this machine, as agent_setup.sh sees it."""
    import platform
    os_name = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(platform.system())
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine().lower())
    if not os_name or not arch or f"{os_name}_{arch}" not in PLATFORM_ASSETS:
        return None
    return f"{os_name}_{arch}", "gitleaks.exe" if os_name == "windows" else "gitleaks"


def fake_archive(asset: str, exe: str) -> bytes:
    payload = f"#!/bin/sh\necho {VERSION}\n".encode()
    buf = io.BytesIO()
    if asset.endswith(".zip"):
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(exe, payload)
    else:
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(exe)
            info.size, info.mode = len(payload), 0o755
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def find_bash() -> str | None:
    if os.name == "nt":  # Git's bash, not the WSL launcher in System32
        exe = shutil.which("git")
        if exe:
            for rel in ("../bin/bash.exe", "../../bin/bash.exe"):
                cand = (Path(exe).resolve().parent / rel).resolve()
                if cand.exists():
                    return cand.as_posix()
    return shutil.which("bash")


def run_agent_setup(script_text: str, tools: dict | str, archive: bytes, bin_name: str,
                    asset: str, with_checksums: str | None = None) -> dict:
    """Install from a fake release with `script_text` and a tools.json of `tools`.

    Returns exit code, stderr, whether the executable was installed, and which files
    the fake release server was asked for."""
    bash = find_bash()
    with tempfile.TemporaryDirectory(prefix="ds32-") as d:
        d = Path(d)
        deliv = d / "work/scripts/delivery"
        deliv.mkdir(parents=True)
        (deliv / "agent_setup.sh").write_text(script_text, encoding="utf-8", newline="\n")
        (deliv / "tools.json").write_text(
            tools if isinstance(tools, str) else json.dumps({"gitleaks": tools}), encoding="utf-8")
        (deliv / "gate.json").write_text('{"setup": []}\n', encoding="utf-8")
        _Release.files = {asset: archive}
        if with_checksums is not None:
            _Release.files[f"gitleaks_{VERSION}_checksums.txt"] = with_checksums.encode()
        _Release.requests = []
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Release)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            bin_dir = d / "bin"
            env = {**os.environ, "DELIVERY_BIN": bin_dir.as_posix(),
                   "DELIVERY_GITLEAKS_BASE_URL": f"http://127.0.0.1:{srv.server_address[1]}",
                   "PATH": Path(sys.executable).parent.as_posix() + os.pathsep + os.environ.get("PATH", ""),
                   "NO_PROXY": "127.0.0.1,localhost"}
            for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
                env.pop(k, None)
            proc = subprocess.run([bash, (deliv / "agent_setup.sh").as_posix()], cwd=d / "work",
                                  env=env, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=120)
            return {"code": proc.returncode, "err": proc.stderr, "out": proc.stdout,
                    "installed": (bin_dir / bin_name).exists(), "requests": list(_Release.requests)}
        finally:
            srv.shutdown()


def agent_setup_problems(script_text: str) -> list[str]:
    """What is wrong with this agent_setup.sh, judged from a fake release. Empty when it conforms."""
    plat = host_platform()
    if plat is None or find_bash() is None:
        return ["SKIP"]
    key, exe = plat
    asset = f"gitleaks_{VERSION}_{PLATFORM_ASSETS[key]}"
    archive = fake_archive(asset, exe)
    good = hashlib.sha256(archive).hexdigest()
    pins = {k: "0" * 64 for k in PLATFORM_ASSETS}
    problems: list[str] = []

    # 1. the pinned digest is what the archive is checked against, and the checksums file
    #    is never fetched (the server does not even have one).
    pins[key] = good
    r = run_agent_setup(script_text, {"version": VERSION, "sha256": pins}, archive, exe, asset)
    if r["code"] != 0 or not r["installed"]:
        problems.append(f"a matching pin must install (exit {r['code']}): {r['err'][-300:]}")
    if any("checksums" in q for q in r["requests"]):
        problems.append("the pinned form must not download the checksums file")
    if "old form" in r["err"]:
        problems.append("the pinned form must not warn")

    # 2. a pin that does not match the archive installs nothing, and the checksums
    #    file cannot overrule it (the server's file lists the right digest).
    bad = dict(pins, **{key: "1" * 64})
    right_sums = f"{good}  {asset}\n"
    r = run_agent_setup(script_text, {"version": VERSION, "sha256": bad}, archive, exe, asset,
                        with_checksums=right_sums)
    if r["code"] != 2 or r["installed"] or "checksum mismatch" not in r["err"]:
        problems.append(f"a wrong pin must exit 2 with nothing installed (exit {r['code']}, "
                        f"installed {r['installed']}): {r['err'][-300:]}")

    # 3. a pinned form with no pin for this platform is refused, not guessed.
    r = run_agent_setup(script_text, {"version": VERSION, "sha256": {k: v for k, v in pins.items() if k != key}},
                        archive, exe, asset, with_checksums=right_sums)
    if r["code"] != 2 or r["installed"]:
        problems.append(f"a missing platform pin must exit 2 with nothing installed (exit {r['code']})")

    # 4. the old form still installs, with a warning, through the checksums file.
    r = run_agent_setup(script_text, json.dumps({"gitleaks": VERSION}), archive, exe, asset,
                        with_checksums=right_sums)
    if r["code"] != 0 or not r["installed"]:
        problems.append(f"the old form must still install (exit {r['code']}): {r['err'][-300:]}")
    if "old form" not in r["err"]:
        problems.append("the old form must warn")
    if not any("checksums" in q for q in r["requests"]):
        problems.append("the old form must fall back to the checksums file")
    wrong_sums = f"{'1' * 64}  {asset}\n"
    r = run_agent_setup(script_text, json.dumps({"gitleaks": VERSION}), archive, exe, asset,
                        with_checksums=wrong_sums)
    if r["code"] != 2 or r["installed"]:
        problems.append("the old form must still refuse a checksums-file mismatch")
    return problems


@test
def agent_setup_checks_the_archive_against_the_pin():
    script = AGENT_SETUP.read_text(encoding="utf-8").replace("\r\n", "\n")
    problems = agent_setup_problems(script)
    if problems == ["SKIP"]:
        print("SKIP  agent_setup pin path: no bash or an unsupported platform")
        return
    check(not problems, "agent_setup.sh:\n  " + "\n  ".join(problems))


@test
def agent_setup_pin_check_detects_each_defect():
    if agent_setup_problems(AGENT_SETUP.read_text(encoding="utf-8").replace("\r\n", "\n")) == ["SKIP"]:
        print("SKIP  agent_setup pin mutants: no bash or an unsupported platform")
        return
    script = AGENT_SETUP.read_text(encoding="utf-8").replace("\r\n", "\n")
    cases = [
        ("the comparison removed", "if got != want:", "if False:", "wrong pin must exit 2"),
        ("the pin ignored", 'want = pin.lower() or None', 'want = None',
         "a matching pin must install"),
        ("the pin never read", 'print("" if isinstance(g, str) else g.get("sha256", {}).get(sys.argv[2], ""))',
         'print("")', "a matching pin must install"),
        ("no warning for the old form", 'say "warning: tools.json uses the old form;', 'say "note: tools.json;',
         "the old form must warn"),
        ("a missing pin falls through", 'die "tools.json has no pinned SHA-256 for', 'say "tools.json has no pinned SHA-256 for',
         "a missing platform pin must exit 2"),
    ]
    for label, old, new, expect in cases:
        mutated = mutate(script, old, new)
        found = agent_setup_problems(mutated)
        check(any(expect in p for p in found),
              f"mutation '{label}' expecting {expect!r} was not detected; got {found}")


@test
def tools_json_ships_real_pins():
    data = json.loads((DELIVERY / "tools.json").read_text(encoding="utf-8"))["gitleaks"]
    check(isinstance(data, dict), "tools.json must ship in the pinned form")
    check(re.fullmatch(r"\d+\.\d+\.\d+", data["version"]), data["version"])
    check(sorted(data["sha256"]) == sorted(PLATFORM_ASSETS), f"platforms: {sorted(data['sha256'])}")
    for key, digest in data["sha256"].items():
        check(re.fullmatch(r"[0-9a-f]{64}", digest) and len(set(digest)) > 2, f"{key}: {digest!r} is not a real digest")
    check(len(set(data["sha256"].values())) == 5, "each platform needs its own digest")


# ---------------------------------------------------------------------------
# ci_watch: runner health (DL7, warnings only)
# ---------------------------------------------------------------------------

JOBS_PATH = "repos/{owner}/{repo}/actions/runs/5/jobs?per_page=100"
RUNNERS_PATH = "repos/{owner}/{repo}/actions/runners?per_page=100"
LONG_AGO = "2020-01-01T00:00:00Z"


def queued_fixture(labels: list[str], runners, created: str = LONG_AGO, polls: int = 4) -> dict:
    """A run that stays pending for `polls` polls, then succeeds; one queued job."""
    seq = [[run_obj(5, "queued", "")] for _ in range(polls)] + [[run_obj(5, "completed", "success")]]
    job = {"id": 11, "name": "build", "status": "queued", "created_at": created, "labels": labels}
    api = {JOBS_PATH: {"jobs": [job]}}
    if runners == "error":
        api[RUNNERS_PATH] = {"__error": "HTTP 403: Must have admin rights to Repository."}
    elif runners is not None:
        api[RUNNERS_PATH] = {"runners": [
            {"status": st, "labels": [{"name": n} for n in lab]} for st, lab in runners]}
    return {"run_list": seq, "api": api}


def watch_queued(fx: dict):
    sb = Sandbox()
    try:
        rc, out, err = watch(sb, fx)
        return rc, out, err
    finally:
        sb.close()


@test
def watch_warns_once_when_no_online_runner_has_the_labels():
    rc, out, err = watch_queued(queued_fixture(
        ["self-hosted", "gpu"], [("online", ["self-hosted", "linux"]), ("offline", ["self-hosted", "gpu"])]))
    expect_exit(rc, 0, out, err)  # a warning never changes the exit code
    check(out.count("WARNING") == 1, f"expected exactly one warning over several polls: {out}")
    check("gpu" in out and "no online runner" in out, f"warning must name the labels: {out}")


@test
def watch_no_warning_when_an_online_runner_has_the_labels():
    rc, out, err = watch_queued(queued_fixture(
        ["self-hosted", "gpu"], [("online", ["self-hosted", "gpu", "linux"])]))
    expect_exit(rc, 0, out, err)
    check("WARNING" not in out, f"a runner carries the labels, no warning expected: {out}")


@test
def watch_says_queued_10_min_when_runners_cannot_be_listed():
    rc, out, err = watch_queued(queued_fixture(["self-hosted", "gpu"], "error"))
    expect_exit(rc, 0, out, err)
    check("WARNING" in out and "queued 10+ min" in out and "could not be listed" in out,
          f"expected the 10+ min warning with the reason: {out}")
    check(out.count("WARNING") == 1, f"warn once: {out}")


@test
def watch_no_warning_for_a_job_queued_under_the_limit():
    rc, out, err = watch_queued(queued_fixture(
        ["self-hosted", "gpu"], [("online", ["self-hosted", "linux"])], created="2999-01-01T00:00:00Z"))
    expect_exit(rc, 0, out, err)
    check("WARNING" not in out, f"a job queued for a moment must not warn: {out}")


@test
def watch_no_warning_for_a_queued_github_hosted_job():
    rc, out, err = watch_queued(queued_fixture(["ubuntu-latest"], []))
    expect_exit(rc, 0, out, err)
    check("WARNING" not in out, f"hosted labels count as available: {out}")


def watch_runner_detectors() -> list:
    return [watch_warns_once_when_no_online_runner_has_the_labels,
            watch_no_warning_when_an_online_runner_has_the_labels,
            watch_says_queued_10_min_when_runners_cannot_be_listed,
            watch_no_warning_for_a_job_queued_under_the_limit,
            watch_no_warning_for_a_queued_github_hosted_job]


@test
def watch_runner_health_mutants_are_detected():
    global CI_WATCH
    original = CI_WATCH.read_text(encoding="utf-8").replace("\r\n", "\n")
    cases = [
        ("warns on every poll", " or jid in warned:", ":"),
        ("a runner with the labels is ignored",
         "elif labels and not any(runner_health.runner_carries(r, labels) for r in runners):",
         "elif labels:"),
        ("the age limit ignored", "if age is None or age < threshold:", "if age is None:"),
        ("hosted labels are checked", "if labels and runner_health.is_hosted(labels):", "if False:"),
        ("an unlistable runner list stays silent", "if runners is None:\n                print(",
         "if False:\n                print("),
        ("the warning is never recorded", "            warned.add(jid)\n", "            pass\n"),
    ]
    saved = CI_WATCH
    with tempfile.TemporaryDirectory(prefix="dl7-") as d:
        shutil.copy(DELIVERY / "runner_health.py", Path(d) / "runner_health.py")
        for label, old, new in cases:
            path = Path(d) / "ci_watch.py"
            path.write_text(mutate(original, old, new), encoding="utf-8", newline="\n")
            CI_WATCH = path
            try:
                caught = False
                for fn in watch_runner_detectors():
                    try:
                        fn()
                    except Exception:  # noqa: BLE001 - any failing test is a detection
                        caught = True
                        break
                check(caught, f"mutation '{label}' was not detected by any runner-health test")
            finally:
                CI_WATCH = saved


# ---------------------------------------------------------------------------

def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
        except Exception:  # noqa: BLE001 - report every failing test
            failed += 1
            print(f"FAIL  {fn.__name__}")
            print("      " + traceback.format_exc().strip().replace("\n", "\n      "))
        else:
            print(f"ok    {fn.__name__}")
    print(f"\n{len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
