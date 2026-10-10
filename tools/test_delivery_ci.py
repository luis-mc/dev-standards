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
    deliberately broken copies and must report each defect.

Run:  python3 tools/test_delivery_ci.py
"""
from __future__ import annotations

import http.server
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLING = (ROOT / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling")
DELIVERY = TOOLING / "shared/scripts/delivery"
CI_WATCH = DELIVERY / "ci_watch.py"
CI_SKIP = DELIVERY / "ci_skip_check.py"
REACH = DELIVERY / "reach_check.py"
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
        rc, out, err = watch(sb, {"run_list": [[run_obj(1, "completed", "skipped")]]})
        expect_exit(rc, 0, out, err)
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
        if not re.search(r"GH_TOKEN: \$\{\{ github\.token \}\}", d):
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
        if not re.search(r"^    needs: decide\s*$", block, re.M):
            problems.append(f"job {name}: missing 'needs: decide'")
        if f"\n    if: {IF_COND}\n" not in block:
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

    # triggers, paths-ignore, concurrency kept
    if text.count("docs/**") < 2:
        problems.append("docs/** must stay in paths-ignore for pull_request and push")
    if "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" not in text:
        problems.append("concurrency must cancel only pull-request runs")
    if "branches: [main]" not in text or "ready_for_review" not in text:
        problems.append("push/pull_request triggers changed")

    if track == "ts":
        problems += check_ts_e2e(text, jobs)
    return problems


def check_ts_e2e(text: str, jobs: dict[str, str]) -> list[str]:
    problems = []
    e = jobs.get("e2e")
    if e is None:
        return ["ts: e2e job missing"]
    if not re.search(r"^    name: web E2E \(§11\.2\)\s*$", e, re.M):
        problems.append("ts: e2e job must be named 'web E2E (§11.2)'")
    if re.search(r"^    continue-on-error:", e, re.M):
        problems.append("ts: e2e must not be continue-on-error at job level")
    if "advisory" in e.lower():
        problems.append("ts: e2e is still described as advisory")
    steps = split_steps(e)
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
        ("ts", ts, "cancel only pull-request",
         lambda t: mutate(t, "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
                          "cancel-in-progress: true")),
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
         lambda t: mutate(t, "        run: pnpm exec playwright test\n",
                          "        continue-on-error: true\n        run: pnpm exec playwright test\n")),
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
