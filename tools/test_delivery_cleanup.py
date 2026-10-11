#!/usr/bin/env python3
"""Prove cleanup.py, join.py's call to it and train-cleanup.yml do what CONTRACT.md says.

Every scenario builds throwaway repositories in a temp directory: a bare "origin"
(its main branch deletable, so only the script's own rules protect it), a working
clone holding the delivery scripts, linked worktrees (locked, dirty, with unpushed
commits, detached) and a stub `gh` on PATH that answers `gh pr list` / `gh pr view`
from a JSON fixture. Nothing here touches a real repository or GitHub.

"Every check must be able to fail" is proved as in tools/test_delivery_gate.py:
scenarios hold both sides of a rule (finished and kept), then the mutation pass
copies the scripts, breaks one safety rule in the copy and requires the scenario
that guards it to report a failure. The workflow checker is run on deliberately
broken copies and must name each defect.

Run:  python3 tools/test_delivery_cleanup.py [--no-mutants] [-k SUBSTRING]
Exit: 0 all passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_delivery_gate as tdg  # noqa: E402  (its harness: T, run, Box, mutated_shared)
from test_delivery_gate import PY, SHARED, T, run  # noqa: E402

ZERO = "0" * 40
WORKFLOW = SHARED / ".github/workflows/train-cleanup.yml"
TS_CI = tdg.TOOLING / "ts/.github/workflows/ci.yml"
_TMP = Path(tempfile.mkdtemp(prefix="delivery-cleanup-test-"))

GATE_JSON = {
    "schema": 1, "track": "test", "default_branch": "main", "setup": [],
    "packages": {"kind": "pnpm-workspace"}, "widen_on": [], "ui_paths": [],
    "steps": [{"name": "guards", "scope": "always", "run": "true"}],
}

def exit_is(t: T, label: str, r, want: int) -> bool:
    """Check an exit code; on a mismatch the detail carries the script's own output."""
    return t.check(label, r.code == want,
                   "expected exit %d, got %d\n--- stderr ---\n%s\n--- stdout ---\n%s"
                   % (want, r.code, r.err.strip(), r.out.strip()[:600]))


# --------------------------------------------------------------------------
# stub gh
# --------------------------------------------------------------------------

STUB_GH = r'''
import json, os, sys

argv = sys.argv[1:]
with open(os.environ["GH_STUB_FIXTURE"], encoding="utf-8") as fh:
    fx = json.load(fh)
with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\n")


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


if fx.get("all_error"):
    fail("HTTP 502: bad gateway")
if argv[:2] == ["pr", "list"]:
    key = ("head:" + opt("--head")) if opt("--head") else ("base:" + opt("--base"))
    if key in fx.get("errors", []):
        fail("HTTP 500 for " + key)
    if key in fx.get("garbage", []):
        print("<html>not json</html>")
    else:
        print(json.dumps(fx.get("lists", {}).get(key, [])))
elif argv[:2] == ["pr", "view"]:
    view = fx.get("views", {}).get(argv[2])
    if view is None:
        fail("no pull request #" + argv[2])
    print(json.dumps(view))
else:
    fail("stub gh: unexpected call " + " ".join(argv))
'''


class Stub:
    """A stub `gh` (script + shim) and its fixture, in a directory of its own."""

    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="gh-", dir=_TMP))
        (self.dir / "gh.py").write_text(STUB_GH, encoding="utf-8")
        if os.name == "nt":
            (self.dir / "gh.cmd").write_text('@"%s" "%%~dp0gh.py" %%*\r\n' % sys.executable, encoding="utf-8")
        else:
            shim = self.dir / "gh"
            shim.write_text('#!/bin/sh\nexec "%s" "$(dirname "$0")/gh.py" "$@"\n' % sys.executable, encoding="utf-8")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.fx: dict = {"lists": {}, "views": {}, "errors": [], "garbage": []}
        self.log = self.dir / "gh.log"
        self.fixture = self.dir / "fixture.json"
        self.number = 100
        self.save()

    def save(self) -> None:
        self.fixture.write_text(json.dumps(self.fx), encoding="utf-8")

    def pr(self, head: str, state: str, sha: str, base: str = "main", number: int | None = None) -> int:
        self.number += 1
        n = number or self.number
        item = {"number": n, "state": state, "baseRefName": base, "headRefOid": sha,
                "headRefName": head, "mergedAt": "2026-10-10T10:00:00Z" if state == "MERGED" else None}
        self.fx["lists"].setdefault("head:" + head, []).append(item)
        self.fx["lists"].setdefault("base:" + base, []).append(item)
        self.fx["views"][str(n)] = item
        self.save()
        return n

    def env(self, with_gh: bool = True) -> dict:
        extra: dict = {}
        if with_gh:  # the stub's directory comes first, so it shadows any real gh
            path = os.pathsep.join([str(self.dir), os.environ.get("PATH", "")])
        else:
            path, extra = self._path_without_gh()
        return {"PATH": path, "GH_STUB_FIXTURE": str(self.fixture), "GH_STUB_LOG": str(self.log),
                "PYTHONUTF8": "1", **extra}

    def _path_without_gh(self) -> tuple[str, dict]:
        """A PATH on which `gh` cannot be found but git still can. A directory that
        holds both (/usr/bin on a Linux runner) cannot simply be dropped: git would go
        with it. On POSIX the tools git needs are linked into a directory of their own;
        on Windows (Git for Windows keeps git and gh apart) the offending directories
        are dropped."""
        def has_gh(d: str) -> bool:
            return any((Path(d) / n).exists() for n in ("gh", "gh.exe", "gh.cmd"))

        dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
        kept = [d for d in dirs if not has_gh(d)]
        if os.name == "nt" or len(kept) == len(dirs):
            return os.pathsep.join(kept), {}
        bin_dir = self.dir / "nogh-bin"
        bin_dir.mkdir(exist_ok=True)
        for tool in ("git", "sh"):
            found = shutil.which(tool)
            if found and not (bin_dir / tool).exists():
                (bin_dir / tool).symlink_to(found)
        exec_path = run(["git", "--exec-path"]).out.strip()
        return os.pathsep.join([str(bin_dir), *kept]), {"GIT_EXEC_PATH": exec_path}

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x]


# --------------------------------------------------------------------------
# a throwaway repository
# --------------------------------------------------------------------------

DELIVERY_FILES = ["delivery_common.py", "fast_guards.py", "cleanup.py"]


class World:
    def __init__(self, shared: Path = SHARED, gate_default: str = "main", origin_head: str = "main"):
        self.root = Path(tempfile.mkdtemp(prefix="world-", dir=_TMP))
        self.origin = self.root / "origin.git"
        self.work = self.root / "work"
        self.stub = Stub()
        run(["git", "init", "-q", "--bare", "-b", "main", self.origin])
        # the default branch is deletable here: only cleanup.py's own rules protect it
        run(["git", "--git-dir", self.origin.as_posix(), "config", "receive.denyDeleteCurrent", "ignore"])
        self.work.mkdir()
        self.g("init", "-q", "-b", "main")
        self.g("remote", "add", "origin", self.origin.as_posix())
        d = self.work / "scripts/delivery"
        d.mkdir(parents=True)
        for name in DELIVERY_FILES:
            tdg.Box.copy_text(shared / "scripts/delivery" / name, d / name)
        (d / "gate.json").write_text(json.dumps({**GATE_JSON, "default_branch": gate_default}), encoding="utf-8")
        self.write(".gitignore", ".claude/worktrees/\n.delivery/\n__pycache__/\n")
        self.write("README.md", "hello\n")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "init")
        self.g("push", "-q", "-u", "origin", "main")
        run(["git", "--git-dir", self.origin.as_posix(), "symbolic-ref", "HEAD", "refs/heads/" + origin_head])
        self.seq = 0

    # -- git helpers -------------------------------------------------------
    def g(self, *args: str, cwd: Path | None = None, check: bool = True, input_text: str | None = None) -> str:
        r = run(["git", *args], cwd=cwd or self.work, input_text=input_text)
        if check and r.code != 0:
            raise RuntimeError("git %s failed: %s" % (" ".join(args), r.err))
        return r.out.strip()

    def write(self, rel: str, text: str, base: Path | None = None) -> None:
        p = (base or self.work) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, msg: str, cwd: Path | None = None) -> str:
        self.seq += 1
        self.write("f%d.txt" % self.seq, "%s\n" % msg, base=cwd)
        self.g("add", "-A", cwd=cwd)
        self.g("commit", "-q", "-m", msg, cwd=cwd)
        return self.g("rev-parse", "HEAD", cwd=cwd)

    def branch(self, name: str, frm: str = "main", push: bool = True) -> str:
        """A branch with one commit of its own, pushed with an upstream; main stays checked out."""
        self.g("checkout", "-q", "-B", name, frm)
        sha = self.commit("work on " + name)
        if push:
            self.g("push", "-q", "-u", "origin", name)
        self.g("checkout", "-q", "main")
        return sha

    def integration(self, name: str, parts: list[str]) -> str:
        self.g("checkout", "-q", "-B", name, "main")
        for p in parts:
            self.g("merge", "-q", "--no-ff", "-m", "Join " + p, p)
        self.g("push", "-q", "-u", "origin", name)
        self.g("checkout", "-q", "main")
        return self.tip(name)

    def tip(self, branch: str) -> str:
        return self.g("rev-parse", "refs/heads/" + branch)

    def result_ref(self, branch: str) -> None:
        tree = self.g("mktree", input_text="")
        commit = self.g("commit-tree", tree, "-m", "gate result")
        self.g("push", "-q", "--force", "origin", "%s:refs/gate-results/%s" % (commit, branch))

    def worktree(self, name: str, branch: str | None = None, locked: bool = False, detach: bool = False) -> Path:
        path = self.work / ".claude/worktrees" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if detach:
            self.g("worktree", "add", "-q", "--detach", str(path), "main")
        else:
            self.g("worktree", "add", "-q", str(path), branch)
        if locked:
            self.g("worktree", "lock", "--reason", "agent running", str(path))
        return path

    # -- observations ------------------------------------------------------
    def remote_heads(self) -> set[str]:
        out = self.g("ls-remote", "--heads", "origin")
        return {line.split("\trefs/heads/")[1] for line in out.splitlines() if line}

    def remote_results(self) -> set[str]:
        out = self.g("ls-remote", "origin", "refs/gate-results/*")
        return {line.split("\trefs/gate-results/")[1] for line in out.splitlines() if line}

    def local_branches(self) -> set[str]:
        return set(self.g("for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines())

    def worktrees(self) -> set[str]:
        out = self.g("worktree", "list", "--porcelain")
        return {Path(line[len("worktree "):]).name for line in out.splitlines() if line.startswith("worktree ")}

    def snapshot(self) -> tuple:
        return (self.remote_heads(), self.remote_results(), self.local_branches(), self.worktrees())

    # -- running -----------------------------------------------------------
    def cleanup(self, *args: str, gh: bool = True, cwd: Path | None = None):
        return run([PY, str(self.work / "scripts/delivery/cleanup.py"), *args], cwd=cwd or self.work,
                   extra_env=self.stub.env(gh))

    def rows(self, *args: str, gh: bool = True, cwd: Path | None = None):
        """Run with --json; returns (result, {branch: row})."""
        r = self.cleanup(*args, "--json", gh=gh, cwd=cwd)
        try:
            rows = {x["branch"]: x for x in json.loads(r.out)}
        except ValueError:
            rows = {}
        return r, rows


def status(rows: dict, branch: str) -> str:
    row = rows.get(branch)
    return "(no row)" if row is None else row["status"] + (": " + row["detail"] if row["detail"] else "")


def is_kept(rows: dict, branch: str, why: str | None = None) -> bool:
    row = rows.get(branch)
    return bool(row) and row["status"] == "kept" and (why is None or why in row["detail"])


# --------------------------------------------------------------------------
# scenarios: the remote
# --------------------------------------------------------------------------

def sc_classify(t: T, shared: Path) -> None:
    w = World(shared)
    s = w.stub
    d1, d2 = w.branch("feat/d1"), w.branch("feat/d2")
    integ = w.integration("integ", ["feat/d1", "feat/d2"])
    a = w.branch("feat/a")
    old_open = w.branch("feat/open")
    w.branch("feat/closed")
    w.branch("feat/nopr")
    merged_then_more = w.branch("feat/later")
    stray_head = w.branch("feat/stray")
    w.branch("feat/error")
    c1 = w.branch("feat/c1")
    integ2 = w.integration("integ2", ["feat/c1"])
    for b in ("integ", "feat/d1", "feat/d2", "feat/a", "feat/open", "feat/closed", "feat/later", "feat/stray"):
        w.result_ref(b)

    s.pr("integ", "MERGED", integ)                          # the ready pull request, squash-merged
    s.pr("feat/d1", "MERGED", d1, base="integ")              # a draft GitHub marked merged
    s.pr("feat/d2", "CLOSED", d2, base="integ")              # a draft closed when integ was deleted: contained
    s.pr("feat/a", "MERGED", a)
    s.pr("feat/open", "MERGED", old_open)                    # an earlier pull request was merged ...
    s.pr("feat/open", "OPEN", old_open)                      # ... but a new one is open
    s.pr("feat/closed", "CLOSED", w.tip("feat/closed"))      # closed without merging
    s.pr("feat/later", "MERGED", merged_then_more)
    s.pr("feat/stray", "CLOSED", stray_head, base="integ")   # closed into a finished integ, but not contained in it
    s.pr("integ2", "OPEN", integ2)                           # an integration branch still being worked on ...
    s.pr("feat/c1", "CLOSED", c1, base="integ2")             # ... one of its drafts was closed by hand
    s.pr("main", "MERGED", w.tip("main"), base="release")    # nonsense about the default branch must not matter
    s.fx["errors"].append("head:feat/error")
    s.save()
    # feat/later got a commit after its pull request was merged
    w.g("checkout", "-q", "feat/later")
    w.commit("after the merge")
    w.g("push", "-q", "origin", "feat/later")
    w.g("checkout", "-q", "main")

    r, rows = w.rows("--remote-only")
    exit_is(t, "exit 0 although branches were kept", r, 0)
    for b in ("feat/a", "integ", "feat/d1"):
        t.eq("finished (merged pull request): %s" % b, status(rows, b), "deleted")
    t.eq("finished (b): closed draft contained in a finished integration branch", status(rows, "feat/d2"), "deleted")
    t.check("an open pull request keeps the branch, even with an older merged one",
            is_kept(rows, "feat/open", "open pull request"), status(rows, "feat/open"))
    t.check("a pull request closed without merging keeps the branch",
            is_kept(rows, "feat/closed", "closed without merging"), status(rows, "feat/closed"))
    t.check("a closed draft whose commits are not in the integration branch is kept",
            is_kept(rows, "feat/stray", "closed without merging"), status(rows, "feat/stray"))
    t.check("a closed draft whose base is not finished is kept, though the base holds its commits",
            is_kept(rows, "feat/c1", "closed without merging") and is_kept(rows, "integ2", "open pull request"),
            status(rows, "feat/c1"))
    t.check("a branch with no pull request is kept", is_kept(rows, "feat/nopr", "no pull request"), status(rows, "feat/nopr"))
    t.check("commits pushed after the merge keep the branch",
            is_kept(rows, "feat/later", "after the merged"), status(rows, "feat/later"))
    t.check("an error from gh keeps the branch", is_kept(rows, "feat/error", "cannot classify"), status(rows, "feat/error"))
    t.check("the default branch gets no row", "main" not in rows, str(sorted(rows)))
    t.eq("remote: only finished branches are gone",
         w.remote_heads(), {"main", "feat/open", "feat/closed", "feat/nopr", "feat/later", "feat/stray", "feat/error", "feat/c1", "integ2"})
    t.eq("remote: gate-result refs go with their branch, the rest stay",
         w.remote_results(), {"feat/open", "feat/closed", "feat/later", "feat/stray"})
    t.check("--remote-only leaves local branches alone",
            {"feat/a", "feat/d1", "integ"} <= w.local_branches(), str(w.local_branches()))
    t.has("plain output: one row per branch", w.cleanup("--remote-only", "--dry-run").out, "kept: no pull request")

    # a classification that depends on gh being asked per branch with the contract's fields
    heads = [c for c in s.calls() if c[:2] == ["pr", "list"] and "--head" in c]
    t.check("gh pr list --state all --head <branch> --json ...",
            bool(heads) and all("all" in c and "number,state,baseRefName,headRefOid,mergedAt" in c for c in heads),
            str(heads[:1]))


def sc_gh_failure(t: T, shared: Path) -> None:
    w = World(shared)
    s = w.stub
    sha = w.branch("feat/x")
    s.pr("feat/x", "MERGED", sha)
    s.fx["all_error"] = True
    s.save()
    before = w.snapshot()
    r, rows = w.rows()
    exit_is(t, "gh down: exit 0 (nothing decided is not a failure)", r, 0)
    t.check("gh down: the branch is kept", is_kept(rows, "feat/x", "cannot classify"), status(rows, "feat/x"))
    t.eq("gh down: nothing removed anywhere", w.snapshot(), before)
    s.fx["all_error"] = False
    s.fx["garbage"] = ["head:feat/x"]
    s.save()
    r, rows = w.rows("--remote-only")
    t.check("gh answering garbage keeps the branch too", is_kept(rows, "feat/x", "cannot classify"), status(rows, "feat/x"))
    t.eq("... and nothing is removed", w.snapshot(), before)
    s.fx["garbage"] = []
    s.save()
    r, rows = w.rows("--remote-only")
    t.eq("control: gh answering again, the same branch is finished", status(rows, "feat/x"), "deleted")
    t.eq("control: and gone", "feat/x" in w.remote_heads(), False)


def sc_default_branch(t: T, shared: Path) -> None:
    # the default branch is named by gate.json and by the remote's HEAD; each alone must protect it
    for label, gate_default, origin_head in (("gate.json and remote HEAD", "main", "main"),
                                             ("gate.json only", "main", "elsewhere"),
                                             ("remote HEAD only", "trunk", "main")):
        w = World(shared, gate_default=gate_default, origin_head=origin_head)
        w.stub.pr("main", "MERGED", w.tip("main"), base="release")
        w.stub.pr("main", "MERGED", w.tip("main"), base="staging")
        for flags in ([], ["--remote-only"], ["--local"]):
            tag = "%s, %s" % (label, " ".join(flags) or "no flag")
            r, rows = w.rows(*flags)
            exit_is(t, "%s: exit 0" % tag, r, 0)
            t.check("%s: the default branch is never a candidate" % tag, "main" not in rows, str(sorted(rows)))
            t.check("%s: main still on the remote and local" % tag,
                    "main" in w.remote_heads() and "main" in w.local_branches())
    # train of a pull request whose head is the default branch itself
    w2 = World(shared)
    n = w2.stub.pr("main", "MERGED", w2.tip("main"), base="main")
    r, rows = w2.rows("--pr", str(n))
    t.check("--pr with the default branch as head: nothing deleted", "main" in w2.remote_heads() and "main" not in rows)


def sc_failed_deletion(t: T, shared: Path) -> None:
    w = World(shared)
    hook = w.origin / "hooks/pre-receive"
    hook.write_text('#!/bin/sh\nwhile read old new ref; do\n  case "$ref" in\n    *keepme*)\n'
                    '      [ "$new" = "%s" ] && { echo "protected branch" >&2; exit 1; } ;;\n  esac\ndone\nexit 0\n' % ZERO,
                    encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    a, k = w.branch("feat/a"), w.branch("feat/keepme")
    w.stub.pr("feat/a", "MERGED", a)
    w.stub.pr("feat/keepme", "MERGED", k)
    r, rows = w.rows("--remote-only")
    exit_is(t, "a deletion the remote refuses: exit 1", r, 1)
    t.check("... that row says failed", rows.get("feat/keepme", {}).get("status") == "failed", status(rows, "feat/keepme"))
    t.eq("... and the other branch was still deleted", status(rows, "feat/a"), "deleted")
    t.eq("... the refused branch is still there", "feat/keepme" in w.remote_heads(), True)


def sc_pr(t: T, shared: Path) -> None:
    w = World(shared)
    s = w.stub
    d1, d2 = w.branch("feat/d1"), w.branch("feat/d2")
    integ = w.integration("integ", ["feat/d1", "feat/d2"])
    other = w.branch("feat/other")        # finished, but not part of this train
    unrelated = w.branch("feat/unrelated")  # not in the train and not finished
    for b in ("integ", "feat/d1", "feat/d2", "feat/other"):
        w.result_ref(b)
    n = s.pr("integ", "MERGED", integ, number=7)
    s.pr("feat/d1", "MERGED", d1, base="integ")
    s.pr("feat/d2", "CLOSED", d2, base="integ")
    s.pr("feat/other", "MERGED", other)

    # refusals: not merged, merged into something other than the default branch
    s.fx["views"]["8"] = {"number": 8, "state": "OPEN", "baseRefName": "main", "headRefName": "integ", "headRefOid": integ}
    s.fx["views"]["9"] = {"number": 9, "state": "MERGED", "baseRefName": "integ", "headRefName": "feat/d1", "headRefOid": d1}
    s.save()
    before = w.snapshot()
    r = w.cleanup("--pr", "8")
    exit_is(t, "--pr of a pull request that is not merged: exit 2", r, 2)
    t.has("... says why", r.text, "not merged")
    r = w.cleanup("--pr", "9")
    exit_is(t, "--pr of a pull request merged into an integration branch: exit 2", r, 2)
    t.has("... says it is not the default branch", r.text, "default branch")
    r = w.cleanup("--pr", "999")
    exit_is(t, "--pr of an unknown pull request: exit 2", r, 2)
    t.eq("refusals removed nothing", w.snapshot(), before)

    r, rows = w.rows("--remote-only", "--pr", str(n))
    exit_is(t, "--pr N (merged into the default branch): exit 0", r, 0)
    t.eq("the train is exactly the head branch and the branches that had it as base",
         sorted(rows), ["feat/d1", "feat/d2", "integ"])
    t.eq("remote: the train is gone, a finished branch outside it is not",
         w.remote_heads(), {"main", "feat/other", "feat/unrelated"})
    t.eq("gate-result refs of the train are gone", w.remote_results(), {"feat/other"})
    t.eq("--pr lists the children with gh pr list --base", ["integ"] == [c[c.index("--base") + 1] for c in s.calls() if "--base" in c][:1], True)

    # the same train when the platform already deleted the integration branch
    w2 = World(shared)
    d = w2.branch("feat/d")
    ig = w2.integration("integ", ["feat/d"])
    w2.stub.pr("integ", "MERGED", ig, number=3)
    w2.stub.pr("feat/d", "CLOSED", d, base="integ")
    w2.g("push", "-q", "origin", "--delete", "integ")
    r, rows = w2.rows("--remote-only", "--pr", "3")
    t.eq("integration branch already deleted: its closed draft is still removed", w2.remote_heads(), {"main"})
    t.eq("... and the missing branch is reported as already gone", rows.get("integ", {}).get("detail"), "already gone")


def sc_modes(t: T, shared: Path) -> None:
    w = World(shared)
    a, b = w.branch("feat/a"), w.branch("feat/b")
    w.stub.pr("feat/a", "MERGED", a)
    w.stub.pr("feat/b", "MERGED", b)
    w.result_ref("feat/a")
    r = w.cleanup("--local", "--remote-only")
    exit_is(t, "--local with --remote-only: exit 2", r, 2)

    r, rows = w.rows("--remote-only")
    t.eq("--remote-only: remote branches removed", "feat/a" in w.remote_heads() or "feat/b" in w.remote_heads(), False)
    t.eq("--remote-only: local branches kept", {"feat/a", "feat/b"} <= w.local_branches(), True)
    w2 = World(shared)
    a2 = w2.branch("feat/a")
    w2.stub.pr("feat/a", "MERGED", a2)
    w2.result_ref("feat/a")
    r, rows = w2.rows("--local")
    t.eq("--local: local branch removed", "feat/a" in w2.local_branches(), False)
    t.eq("--local: remote branch and result ref kept",
         ("feat/a" in w2.remote_heads(), "feat/a" in w2.remote_results()), (True, True))
    t.eq("--local: still reported as deleted", status(rows, "feat/a"), "deleted")

    # neither flag: both sides, in one row
    w3 = World(shared)
    a3 = w3.branch("feat/a")
    w3.stub.pr("feat/a", "MERGED", a3)
    w3.result_ref("feat/a")
    r, rows = w3.rows()
    t.eq("no flag: remote and local removed",
         ("feat/a" in w3.remote_heads(), "feat/a" in w3.remote_results(), "feat/a" in w3.local_branches()),
         (False, False, False))
    t.eq("one row for the branch", list(rows), ["feat/a"])


def sc_dry_run(t: T, shared: Path) -> None:
    w = World(shared)
    a = w.branch("feat/a")
    w.branch("feat/open")
    w.result_ref("feat/a")
    wt = w.worktree("agent-a", "feat/a", locked=True)
    w.stub.pr("feat/a", "MERGED", a)
    w.stub.pr("feat/open", "OPEN", w.tip("feat/open"))
    before = w.snapshot()
    r, rows = w.rows("--dry-run")
    exit_is(t, "--dry-run: exit 0", r, 0)
    t.eq("--dry-run: a finished branch is 'would delete'", status(rows, "feat/a"), "would delete")
    t.check("--dry-run: the row names what would go",
            all(x in rows["feat/a"]["removed"] for x in ("remote branch", "gate-result ref", "local branch")),
            str(rows.get("feat/a")))
    t.check("--dry-run: a kept branch is still kept", is_kept(rows, "feat/open"), status(rows, "feat/open"))
    t.eq("--dry-run: remote, refs, local branches and worktrees unchanged", w.snapshot(), before)
    t.check("--dry-run: the worktree directory is still there", wt.is_dir())
    t.has("--dry-run: plain output says would delete", w.cleanup("--dry-run").out, "would delete")
    # control: the same run for real removes all of it
    r, rows = w.rows()
    t.eq("control (no --dry-run): deleted", status(rows, "feat/a"), "deleted")
    t.eq("control: everything of feat/a is gone", (w.remote_heads(), w.remote_results(), w.local_branches(), wt.exists()),
         ({"main", "feat/open"}, set(), {"main", "feat/open"}, False))


# --------------------------------------------------------------------------
# scenarios: local branches and worktrees
# --------------------------------------------------------------------------

def sc_worktrees(t: T, shared: Path) -> None:
    w = World(shared)
    s = w.stub
    for b in ("clean", "dirty", "staged", "unpushed", "openpr", "lockedclean", "lockeddirty", "nobody"):
        s.pr("agent/" + b, "MERGED" if b != "openpr" else "OPEN", w.branch("agent/" + b))
    paths = {
        "clean": w.worktree("clean", "agent/clean"),
        "dirty": w.worktree("dirty", "agent/dirty"),
        "staged": w.worktree("staged", "agent/staged"),
        "unpushed": w.worktree("unpushed", "agent/unpushed"),
        "openpr": w.worktree("openpr", "agent/openpr", locked=True),
        "lockedclean": w.worktree("lockedclean", "agent/lockedclean", locked=True),
        "lockeddirty": w.worktree("lockeddirty", "agent/lockeddirty", locked=True),
        "detached": w.worktree("artifacts-record", detach=True),
    }
    w.write("scratch.txt", "untracked\n", base=paths["dirty"])
    w.write("README.md", "edited\n", base=paths["staged"])
    w.g("add", "README.md", cwd=paths["staged"])
    w.commit("never pushed", cwd=paths["unpushed"])
    w.write("scratch.txt", "untracked\n", base=paths["lockeddirty"])
    w.write("scratch.txt", "untracked\n", base=paths["detached"])  # dirty and detached: must stay untouched
    main_head = w.g("rev-parse", "HEAD")

    r, rows = w.rows("--local")
    exit_is(t, "exit 0 with worktrees kept", r, 0)
    t.eq("clean worktree on a finished branch: removed", (status(rows, "agent/clean"), paths["clean"].exists()),
         ("deleted", False))
    t.eq("... and its branch", "agent/clean" in w.local_branches(), False)
    t.eq("locked, clean, pushed worktree on a finished branch: removed",
         (status(rows, "agent/lockedclean"), paths["lockedclean"].exists(), "agent/lockedclean" in w.local_branches()),
         ("deleted", False, False))
    t.check("untracked file keeps the worktree and its branch",
            is_kept(rows, "agent/dirty", "uncommitted") and paths["dirty"].exists() and "agent/dirty" in w.local_branches(),
            status(rows, "agent/dirty"))
    t.check("staged change keeps the worktree and its branch",
            is_kept(rows, "agent/staged", "uncommitted") and paths["staged"].exists() and "agent/staged" in w.local_branches(),
            status(rows, "agent/staged"))
    t.check("a locked dirty worktree is kept (the lock is no licence)",
            is_kept(rows, "agent/lockeddirty", "uncommitted") and paths["lockeddirty"].exists(),
            status(rows, "agent/lockeddirty"))
    t.check("commits not on the remote keep the worktree and its branch",
            is_kept(rows, "agent/unpushed", "not on the remote") and paths["unpushed"].exists()
            and "agent/unpushed" in w.local_branches(), status(rows, "agent/unpushed"))
    t.check("an open pull request keeps its (locked) worktree",
            is_kept(rows, "agent/openpr", "open pull request") and paths["openpr"].exists(), status(rows, "agent/openpr"))
    t.check("a detached worktree is never touched, dirty or not",
            paths["detached"].is_dir() and (paths["detached"] / "scratch.txt").exists() and "artifacts-record" in w.worktrees())
    t.eq("a finished branch with no worktree: local branch removed", "agent/nobody" in w.local_branches(), False)
    t.check("the main working tree and main are intact",
            w.g("rev-parse", "HEAD") == main_head and "main" in w.local_branches() and (w.work / "README.md").exists())
    t.eq("worktree list was pruned of the removed ones", w.worktrees() & {"clean", "lockedclean"}, set())
    t.eq("--local deleted nothing on the remote", "agent/clean" in w.remote_heads(), True)

    # a finished branch checked out in the main working tree, and in the tree the script runs in
    w2 = World(shared)
    sha = w2.branch("feat/main-tree")
    w2.stub.pr("feat/main-tree", "MERGED", sha)
    runner = w2.worktree("runner", detach=True)  # run from elsewhere, so only the main-tree rule can keep it
    w2.g("checkout", "-q", "feat/main-tree")
    r, rows = w2.rows("--local", cwd=runner)
    t.check("a branch checked out in the main working tree is kept",
            is_kept(rows, "feat/main-tree") and "feat/main-tree" in w2.local_branches() and r.code == 0, status(rows, "feat/main-tree"))
    w2.g("checkout", "-q", "main")
    sha2 = w2.branch("feat/here")
    w2.stub.pr("feat/here", "MERGED", sha2)
    here = w2.worktree("here", "feat/here")
    r, rows = w2.rows("--local", cwd=here)
    t.check("a branch checked out in the tree the script runs in is kept",
            is_kept(rows, "feat/here") and here.exists(), status(rows, "feat/here"))

    # an unreachable worktree directory is pruned, and its finished branch goes
    w3 = World(shared)
    sha3 = w3.branch("feat/gone")
    w3.stub.pr("feat/gone", "MERGED", sha3)
    gone = w3.worktree("gone", "feat/gone")
    tdg.rmtree(gone)
    r, rows = w3.rows("--local")
    t.eq("a worktree whose directory vanished: pruned, branch deleted",
         (status(rows, "feat/gone"), "feat/gone" in w3.local_branches(), "gone" in w3.worktrees()),
         ("deleted", False, False))
    # `git worktree prune` runs at the end whatever was decided
    w4 = World(shared)
    sha4 = w4.branch("feat/open")
    w4.stub.pr("feat/open", "OPEN", sha4)
    stale = w4.worktree("stale", "feat/open")
    tdg.rmtree(stale)
    t.eq("control: git still lists the vanished worktree", "stale" in w4.worktrees(), True)
    r, rows = w4.rows("--local")
    t.check("a stale worktree entry of a kept branch is pruned too",
            "stale" not in w4.worktrees() and is_kept(rows, "feat/open"), status(rows, "feat/open"))
    stale2 = w4.worktree("stale2", "feat/open")
    tdg.rmtree(stale2)
    r, rows = w4.rows("--local", "--dry-run")
    t.eq("--dry-run does not prune", "stale2" in w4.worktrees(), True)


def sc_local_without_gh(t: T, shared: Path) -> None:
    """Without a working gh, --local deletes nothing: it only lists what gh would have to confirm."""
    w = World(shared)
    w.branch("feat/gone")      # merged and deleted on the remote: upstream gone
    w.branch("feat/live")      # upstream still there
    w.branch("feat/local", push=False)  # never pushed
    w.worktree("gone", "feat/gone")
    w.g("push", "-q", "origin", "--delete", "feat/gone")
    before = w.snapshot()
    r, rows = w.rows("--local", gh=False)
    exit_is(t, "no gh, --local: exit 0", r, 0)
    gone = rows.get("feat/gone") or {}
    t.eq("no gh: a branch whose upstream is gone is listed as needing gh",
         (gone.get("status"), gone.get("detail")), ("would delete", "needs gh to confirm"))
    t.eq("... and nothing is removed: branch, worktree, remote", w.snapshot(), before)
    t.check("no gh: a branch whose upstream exists is kept", is_kept(rows, "feat/live", "cannot classify"), status(rows, "feat/live"))
    t.check("no gh: a branch that was never pushed is kept", is_kept(rows, "feat/local", "cannot classify"), status(rows, "feat/local"))
    t.eq("no gh: the main branch is not listed", "main" in rows, False)
    r = w.cleanup("--local", gh=False)
    t.has("the row reads 'would delete (needs gh to confirm)'", r.out, "feat/gone  would delete (needs gh to confirm)")
    t.eq("... and the run changed nothing", w.snapshot(), before)
    r = w.cleanup("--local", "--dry-run", gh=False)
    t.has("--dry-run says the same", r.out, "feat/gone  would delete (needs gh to confirm)")
    r = w.cleanup(gh=False)
    exit_is(t, "no gh, no mode flag: exit 0", r, 0)
    t.has("... the local-only branch is listed the same way", r.out, "feat/gone  would delete (needs gh to confirm)")
    t.eq("... and nothing is removed", w.snapshot(), before)

    # a gh that is installed but failing is no better than none
    w3 = World(shared)
    w3.branch("feat/gone")
    w3.branch("feat/live")
    w3.worktree("gone", "feat/gone")
    w3.g("push", "-q", "origin", "--delete", "feat/gone")
    w3.stub.fx["all_error"] = True
    w3.stub.save()
    before = w3.snapshot()
    r, rows = w3.rows("--local")
    exit_is(t, "gh failing, --local: exit 0", r, 0)
    t.eq("gh failing: an upstream-gone branch is listed as needing gh",
         (rows.get("feat/gone") or {}).get("detail"), "needs gh to confirm")
    t.check("gh failing: a branch whose upstream exists is kept", is_kept(rows, "feat/live", "cannot classify"), status(rows, "feat/live"))
    t.eq("gh failing: nothing is removed", w3.snapshot(), before)

    # gh working: the pull request decides, as before
    w4 = World(shared)
    done = w4.branch("feat/done")
    w4.branch("feat/nopr")
    w4.worktree("done", "feat/done")
    w4.g("push", "-q", "origin", "--delete", "feat/done")
    w4.g("push", "-q", "origin", "--delete", "feat/nopr")
    w4.stub.pr("feat/done", "MERGED", done)
    r, rows = w4.rows("--local")
    t.eq("gh working: a merged branch is deleted", status(rows, "feat/done"), "deleted")
    t.eq("... with its worktree", ("feat/done" in w4.local_branches(), "done" in w4.worktrees()), (False, False))
    t.check("gh working: an upstream-gone branch with no pull request is kept, not deleted",
            is_kept(rows, "feat/nopr", "no pull request"), status(rows, "feat/nopr"))
    t.eq("... and still there", "feat/nopr" in w4.local_branches(), True)

    w2 = World(shared)
    sha = w2.branch("feat/a")
    w2.stub.pr("feat/a", "MERGED", sha)
    before = w2.snapshot()
    r, rows = w2.rows(gh=False)
    t.eq("no gh, remote mode: nothing can be classified, nothing is removed", w2.snapshot(), before)
    t.check("... and the branch is listed as kept", is_kept(rows, "feat/a"), status(rows, "feat/a"))
    r, rows = w2.rows("--remote-only", gh=False)
    t.check("... --remote-only too", is_kept(rows, "feat/a", "cannot classify"), status(rows, "feat/a"))


# --------------------------------------------------------------------------
# scenarios: scaffolding branches and stale push-check folders
# --------------------------------------------------------------------------

def scaffold_world(shared: Path):
    """Branches an isolated agent leaves: empty ones (with and without a clean worktree), one with a
    commit, one with a dirty worktree, one whose name is on the remote, a closed pull request."""
    w = World(shared)
    w.g("branch", "worktree-agent-bare", "main")
    w.g("branch", "worktree-agent-clean", "main")
    wt_clean = w.worktree("agent-clean", "worktree-agent-clean")
    w.g("branch", "worktree-agent-dirty", "main")
    wt_dirty = w.worktree("agent-dirty", "worktree-agent-dirty")
    w.write("scratch.txt", "untracked\n", base=wt_dirty)
    w.branch("worktree-agent-work", push=False)           # one commit of its own, never pushed
    w.g("branch", "worktree-agent-onremote", "main")
    w.g("push", "-q", "origin", "worktree-agent-onremote")  # empty, but its name is on the remote
    w.g("branch", "worktree-agent-closed", "main")
    w.stub.pr("worktree-agent-closed", "CLOSED", w.tip("worktree-agent-closed"))
    return w, wt_clean, wt_dirty


def sc_scaffolding(t: T, shared: Path) -> None:
    for label, gh in (("with gh", True), ("without gh", False)):
        for flags in (["--local"], []):
            tag = "%s%s" % (label, " " + " ".join(flags) if flags else "")
            w, wt_clean, wt_dirty = scaffold_world(shared)
            r, rows = w.rows(*flags, gh=gh)
            exit_is(t, "%s: exit 0" % tag, r, 0)
            t.eq("%s: an empty scaffolding branch is removed" % tag,
                 (status(rows, "worktree-agent-bare"), "worktree-agent-bare" in w.local_branches()), ("deleted", False))
            t.eq("%s: so is one held by a clean worktree, worktree included" % tag,
                 (status(rows, "worktree-agent-clean"), "worktree-agent-clean" in w.local_branches(), wt_clean.exists()),
                 ("deleted", False, False))
            t.check("%s: a commit not on main keeps the branch" % tag,
                    is_kept(rows, "worktree-agent-work", "commits not on main")
                    and "worktree-agent-work" in w.local_branches(), status(rows, "worktree-agent-work"))
            t.check("%s: a dirty worktree keeps its branch" % tag,
                    is_kept(rows, "worktree-agent-dirty", "uncommitted") and wt_dirty.exists()
                    and "worktree-agent-dirty" in w.local_branches(), status(rows, "worktree-agent-dirty"))
            t.check("%s: a name on the remote is an ordinary branch (kept, not scaffolding)" % tag,
                    "worktree-agent-onremote" in w.local_branches() and "worktree-agent-onremote" in w.remote_heads()
                    and is_kept(rows, "worktree-agent-onremote"), status(rows, "worktree-agent-onremote"))
            t.check("%s: main is untouched" % tag, "main" in w.local_branches() and "main" not in rows)
            if gh:
                t.check("%s: a pull request closed without merging is not scaffolding" % tag,
                        is_kept(rows, "worktree-agent-closed", "closed without merging")
                        and "worktree-agent-closed" in w.local_branches(), status(rows, "worktree-agent-closed"))
                t.check("%s: the remote-named one is kept as 'no pull request'" % tag,
                        is_kept(rows, "worktree-agent-onremote", "no pull request"), status(rows, "worktree-agent-onremote"))
            t.eq("%s: the remote is untouched" % tag, "worktree-agent-onremote" in w.remote_heads() and "main" in w.remote_heads(), True)

    # --remote-only never touches local branches
    w, _, _ = scaffold_world(shared)
    before = w.snapshot()
    r, rows = w.rows("--remote-only")
    t.eq("--remote-only leaves scaffolding branches alone", w.snapshot(), before)

    # dry run
    w, wt_clean, _ = scaffold_world(shared)
    before = w.snapshot()
    r, rows = w.rows("--dry-run", "--local")
    t.eq("--dry-run: an empty scaffolding branch is 'would delete'", status(rows, "worktree-agent-bare"), "would delete")
    t.eq("--dry-run: nothing is changed", w.snapshot(), before)
    t.check("--dry-run: the worktree is still there", wt_clean.is_dir())
    t.has("--dry-run: plain output says would delete", w.cleanup("--dry-run", "--local", gh=False).out,
          "worktree-agent-bare  would delete")

    # a branch strictly behind the remote's default branch holds nothing
    w, _, _ = scaffold_world(shared)
    old = w.g("rev-parse", "main")
    w.commit("main moves on")
    w.g("push", "-q", "origin", "main")
    w.g("branch", "worktree-agent-old", old)
    r, rows = w.rows("--local", gh=False)
    t.eq("a branch strictly behind the default branch holds nothing: removed",
         (status(rows, "worktree-agent-old"), "worktree-agent-old" in w.local_branches()), ("deleted", False))

    # the default branch on the remote decides, not the local one
    w, _, _ = scaffold_world(shared)
    w.commit("local main only, not pushed")
    w.g("branch", "worktree-agent-ahead")  # at the unpushed local main
    r, rows = w.rows("--local", gh=False)
    t.check("a commit only on the local default branch (not on the remote's) keeps the branch",
            is_kept(rows, "worktree-agent-ahead", "commits not on main"), status(rows, "worktree-agent-ahead"))


def _mklink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        p = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if p.returncode != 0:
            raise RuntimeError("mklink failed: %s" % p.stderr)
    else:
        os.symlink(target, link, target_is_directory=True)


def _unlink_dir(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        os.unlink(link)


def sc_push_check_sweep(t: T, shared: Path) -> None:
    w = World(shared)
    sha = w.g("rev-parse", "HEAD")
    nm = w.work / "node_modules"
    (nm / "pkg").mkdir(parents=True)
    (nm / "pkg/index.js").write_text("keep\n", encoding="utf-8")
    deep = w.work / "deps-web"
    (deep / "dep").mkdir(parents=True)
    (deep / "dep/x.js").write_text("keep\n", encoding="utf-8")
    dead = subprocess.Popen([PY, "-c", "pass"])
    dead.wait()
    base = w.work / ".delivery/push-check"

    def folder(pid: int, known: bool = True) -> Path:
        path = base / ("%s-%d" % (sha[:12], pid))
        base.mkdir(parents=True, exist_ok=True)
        w.g("worktree", "add", "-q", "--detach", str(path), "main")
        _mklink(path / "node_modules", nm)
        _mklink(path / "apps/web/node_modules", deep)
        if not known:  # git forgot it (its administrative directory is gone); the folder remains
            for adm in (w.work / ".git/worktrees").iterdir():
                gd = (adm / "gitdir").read_text(encoding="utf-8").strip().replace("\\", "/")
                if gd.endswith("%s-%d/.git" % (sha[:12], pid)):
                    shutil.rmtree(adm)
        return path

    def intact(label: str) -> None:
        t.check("... the node_modules targets are intact (%s)" % label,
                (nm / "pkg/index.js").read_text(encoding="utf-8") == "keep\n"
                and (deep / "dep/x.js").read_text(encoding="utf-8") == "keep\n")

    stale = folder(dead.pid)
    live = folder(os.getpid())
    before = w.snapshot()
    r, rows = w.rows("--dry-run", "--local")
    key = "push-check " + stale.name
    t.eq("--dry-run: a stale folder is 'would delete'", status(rows, key), "would delete")
    t.check("--dry-run: ... and still there with its links", stale.is_dir() and (stale / "node_modules/pkg").is_dir())
    t.eq("--dry-run: nothing else changes", w.snapshot(), before)
    t.has("--dry-run: plain output", w.cleanup("--dry-run", "--local").out, "push-check %s  would delete" % stale.name)

    r, rows = w.rows("--local")
    exit_is(t, "sweep: exit 0", r, 0)
    t.eq("a stale folder (dead pid) is deleted", (status(rows, key), stale.exists()), ("deleted", False))
    intact("stale")
    t.check("... and git no longer lists it", stale.name not in w.worktrees())
    t.check("a folder whose pid is alive is kept",
            is_kept(rows, "push-check " + live.name, "running") and live.is_dir()
            and (live / "node_modules/pkg/index.js").is_file(), status(rows, "push-check " + live.name))
    intact("live")

    # git forgot the folder: the folder goes, and the worktree list is pruned
    forgotten = folder(dead.pid + 100000, known=False)
    t.check("control: git does not list the forgotten folder",
            all(forgotten.name not in x for x in w.g("worktree", "list").splitlines()))
    r, rows = w.rows()  # default mode sweeps too
    k2 = "push-check " + forgotten.name
    t.eq("a folder git no longer knows is removed", (status(rows, k2), forgotten.exists()), ("deleted", False))
    intact("unknown to git")
    t.check("... the live one is still kept", live.is_dir() and (live / "node_modules/pkg/index.js").is_file())

    # a registered worktree whose folder is gone is pruned
    gone = folder(dead.pid + 200000)
    _unlink_dir(gone / "node_modules")
    _unlink_dir(gone / "apps/web/node_modules")
    tdg.rmtree(gone)
    w.rows("--local")
    t.check("a registered worktree with no folder is pruned", gone.name not in w.worktrees())

    # --remote-only does not sweep
    again = folder(dead.pid + 300000)
    w.rows("--remote-only")
    t.check("--remote-only leaves push-check folders alone", again.is_dir())
    # a name that is not <sha>-<pid> is kept
    odd = base / "oddly-named"
    odd.mkdir()
    r, rows = w.rows("--local")
    t.check("a folder not named <sha12>-<pid> is kept", is_kept(rows, "push-check oddly-named") and odd.is_dir(),
            status(rows, "push-check oddly-named"))
    t.eq("... the stale one beside it is deleted", (status(rows, "push-check " + again.name), again.exists()), ("deleted", False))
    intact("end")

# --------------------------------------------------------------------------
# scenarios: join.py
# --------------------------------------------------------------------------

def join_box(shared: Path, cleanup_text: str | None = None):
    box = tdg.Box(shared)
    dst = box.work / "scripts/delivery/cleanup.py"
    if cleanup_text is None:
        tdg.Box.copy_text(shared / "scripts/delivery/cleanup.py", dst)
    else:
        dst.write_text(cleanup_text, encoding="utf-8", newline="\n")
    box.g("add", "-A")
    box.g("commit", "-q", "-m", "add cleanup")
    box.g("push", "-q", "origin", "main")
    box.g("checkout", "-q", "-B", "integ", "main")
    box.push("integ")
    return box


def sc_join_cleanup(t: T, shared: Path) -> None:
    box = join_box(shared)
    stub = Stub()
    old = box.branch("agent/old", {"docs/old.txt": "old\n"})
    box.push("agent/old")
    box.g("checkout", "-q", "integ")
    stub.pr("agent/old", "MERGED", old)
    wt = box.root / "wt-old"
    box.g("worktree", "add", "-q", str(wt), "agent/old")
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = box.script("join.py", "--into", "integ", "feat/a", env=stub.env())
    exit_is(t, "join with a finished local branch: exit 0", r, 0)
    t.eq("... cleanup.py --local ran before the join: worktree and branch gone",
         (wt.exists(), "agent/old" in box.g("branch", "--format=%(refname:short)").split()), (False, False))
    t.check("... and it ran before the first fetch (gh was asked before any merge)", len(stub.calls()) > 0)
    t.eq("... the join itself still happened", box.g("log", "--merges", "--format=%s", "integ").splitlines(), ["Join feat/a"])

    # best effort: a failing cleanup.py never stops the join
    box = join_box(shared, "import sys\nprint('cleanup exploded', file=sys.stderr)\nsys.exit(2)\n")
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = box.script("join.py", "--into", "integ", "feat/a")
    exit_is(t, "cleanup.py exits 2: the join still succeeds", r, 0)
    t.has("... and says it went on", r.text, "going on")
    t.eq("... and joined", box.g("log", "--merges", "--format=%s", "integ").splitlines(), ["Join feat/a"])

    # nothing to clean (no gh): a real cleanup.py failing to classify never stops it either
    box = join_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = box.script("join.py", "--into", "integ", "feat/a", env=Stub().env(with_gh=False))
    exit_is(t, "join without gh: exit 0", r, 0)

    # no gh and a branch whose upstream is gone: the join prints the row and goes on, nothing is removed
    box = join_box(shared)
    box.branch("agent/old", {"docs/old.txt": "old\n"})
    box.push("agent/old")
    box.g("checkout", "-q", "integ")
    box.g("push", "-q", "origin", "--delete", "agent/old")
    wt = box.root / "wt-old"
    box.g("worktree", "add", "-q", str(wt), "agent/old")
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = box.script("join.py", "--into", "integ", "feat/a", env=Stub().env(with_gh=False))
    exit_is(t, "join without gh, a branch with its upstream gone: exit 0", r, 0)
    t.has("... the row is printed", r.out, "agent/old  would delete (needs gh to confirm)")
    t.eq("... the worktree and the branch are still there",
         (wt.exists(), "agent/old" in box.g("branch", "--format=%(refname:short)").split()), (True, True))
    t.eq("... and the join itself happened", box.g("log", "--merges", "--format=%s", "integ").splitlines(), ["Join feat/a"])


# --------------------------------------------------------------------------
# scenario: train-cleanup.yml
# --------------------------------------------------------------------------

def check_workflow(text: str, ci_text: str) -> list[str]:
    """Defects of a train-cleanup.yml against CONTRACT.md (text and regex, no YAML library)."""
    bad = []
    if not re.search(r"^on:\n  pull_request:\n    types: \[closed\]\s*$", text, re.M):
        bad.append("trigger is not pull_request types [closed]")
    if "\n  push:" in text or "workflow_dispatch" in text or "pull_request_target" in text:
        bad.append("extra trigger")
    want_if = "if: github.event.pull_request.merged && github.event.pull_request.base.ref == github.event.repository.default_branch"
    if want_if not in text:
        bad.append("job condition is not merged && base is the default branch")
    perms = re.search(r"^permissions:\n((?:  .+\n)+)", text, re.M)
    if not perms or sorted(perms.group(1).split("\n")[:-1]) != ["  contents: write", "  pull-requests: read"]:
        bad.append("permissions are not contents: write, pull-requests: read")
    if "fetch-depth: 0" not in text:
        bad.append("checkout without fetch-depth: 0")
    for action in ("actions/checkout", "actions/setup-python"):
        if not re.search(r"uses: %s@v\d+\s*$" % re.escape(action), text, re.M):
            bad.append("%s is not pinned to a major version" % action)
    pinned = re.search(r"uses: actions/checkout@(v\d+)", ci_text)
    mine = re.search(r"uses: actions/checkout@(v\d+)", text)
    if not pinned or not mine or pinned.group(1) != mine.group(1):
        bad.append("actions/checkout is pinned differently from the track ci.yml")
    if "python3 scripts/delivery/cleanup.py --remote-only --pr ${{ github.event.pull_request.number }}" not in text:
        bad.append("command is not cleanup.py --remote-only --pr <number>")
    if "GH_TOKEN: ${{ github.token }}" not in text:
        bad.append("GH_TOKEN is not github.token")
    return bad


def sc_workflow(t: T, shared: Path) -> None:
    path = shared / ".github/workflows/train-cleanup.yml"
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    ci = TS_CI.read_bytes().decode("utf-8")
    t.eq("train-cleanup.yml matches the contract", check_workflow(text, ci), [])
    broken = {
        "trigger": text.replace("types: [closed]", "types: [opened]"),
        "extra trigger": text.replace("on:\n", "on:\n  workflow_dispatch:\n", 1),
        "no merged condition": text.replace("github.event.pull_request.merged && ", ""),
        "no base condition": text.replace(" && github.event.pull_request.base.ref == github.event.repository.default_branch", ""),
        "write-all permissions": text.replace("  pull-requests: read\n", "  pull-requests: write\n", 1),
        "shallow checkout": text.replace("fetch-depth: 0", "fetch-depth: 1"),
        "unpinned checkout": text.replace("actions/checkout@v4", "actions/checkout@main"),
        "unpinned python": text.replace("actions/setup-python@v5", "actions/setup-python"),
        "checkout pin differs": text.replace("actions/checkout@v4", "actions/checkout@v3"),
        "wrong command": text.replace("--remote-only ", ""),
        "no pr number": text.replace(" --pr ${{ github.event.pull_request.number }}", ""),
        "no token": text.replace("GH_TOKEN: ${{ github.token }}", "GH_TOKEN: x"),
    }
    for label, body in broken.items():
        t.check("checker reports a defect: %s" % label, body != text and bool(check_workflow(body, ci)),
                "mutation did not change the file" if body == text else "")


def sc_assets(t: T, shared: Path) -> None:
    src = (shared / "scripts/delivery/cleanup.py").read_bytes()
    t.check("cleanup.py keeps sys.dont_write_bytecode = True", b"sys.dont_write_bytecode = True" in src)
    t.check("cleanup.py has a python3 shebang", src.startswith(b"#!/usr/bin/env python3"))
    join = (shared / "scripts/delivery/join.py").read_text(encoding="utf-8")
    t.check("join.py calls cleanup.py --local", '"cleanup.py"' in join and '"--local"' in join)


# --------------------------------------------------------------------------
# mutation pass
# --------------------------------------------------------------------------

D = "scripts/delivery/cleanup.py"
MUTANTS = [
    # classification
    ("an open pull request does not keep a branch", D, "    if opened:\n", "    if False:\n", "classify"),
    ("a closed-unmerged pull request counts as merged", D,
     'merged = [p for p in prs if p.get("state") == "MERGED"]',
     'merged = [p for p in prs if p.get("state") in ("MERGED", "CLOSED")]', "classify"),
    ("a closed draft is finished whatever its commits", D,
     "if contained(ctx, sha, targets):", "if True:", "classify"),
    ("a closed draft into an unfinished base is finished", D,
     "            if not bv.finished:\n                continue\n", "", "classify"),
    ("a branch with no pull request is finished", D,
     'return Verdict(False, "no pull request")', 'return Verdict(True, "no pull request")', "classify"),
    ("a gh error finishes the branch", D,
     'return Verdict(False, "cannot classify (%s)" % exc, cannot_classify=True)',
     'return Verdict(True, "cannot classify (%s)" % exc)',
     "gh_failure"),
    ("commits pushed after the merge are ignored", D,
     "if do_remote and tip and not contained(ctx, tip, v.safe):", "if False:", "classify"),
    ("the remote's HEAD branch is not protected", D,
     'ctx.protected.add(line.split()[1].removeprefix("refs/heads/"))', "pass", "default_branch"),
    ("the default branch of gate.json is not protected", D,
     "Ctx(root, args.remote, args.repo, default, {default}, args.dry_run)",
     "Ctx(root, args.remote, args.repo, default, set(), args.dry_run)", "default_branch"),
    ("gate-result refs are not deleted", D,
     "ctx.result_refs.add(ref[len(dc.RESULT_REF_PREFIX):])", "pass", "classify"),
    ("the exit code ignores failed deletions", D,
     "return dc.EXIT_FAIL if any(r.status == \"failed\" for r in rows) else dc.EXIT_OK", "return dc.EXIT_OK",
     "failed_deletion"),
    # --pr
    ("--pr is ignored", D, "if args.pr is not None:", "if False:", "pr"),
    ("--pr takes only the head branch, not the drafts", D,
     "        queue += [c[\"headRefName\"] for c in children if c.get(\"headRefName\")]\n", "", "pr"),
    ("--pr accepts a pull request that is not merged", D,
     'pr.get("state") != "MERGED"', 'False', "pr"),
    ("--pr accepts a base that is not the default branch", D,
     'pr.get("baseRefName") != ctx.default', "False", "pr"),
    # modes
    ("--remote-only still cleans local branches", D,
     "do_remote, do_local = not args.local, not args.remote_only", "do_remote, do_local = not args.local, True", "modes"),
    ("--local still cleans the remote", D,
     "do_remote, do_local = not args.local, not args.remote_only", "do_remote, do_local = True, not args.remote_only", "modes"),
    ("--local with --remote-only is accepted", D, "if args.local and args.remote_only:", "if False:", "modes"),
    # dry run
    ("--dry-run deletes remote refs", D, "                    if not ctx.dry:\n                        err = push_delete",
     "                    if True:\n                        err = push_delete", "dry_run"),
    ("--dry-run removes worktrees", D, "        if ctx.dry:\n            row.removed.append(\"worktree",
     "        if False:\n            row.removed.append(\"worktree", "dry_run"),
    ("--dry-run deletes local branches", D, "        if not ctx.dry:\n            if len(live) < len(mine):",
     "        if True:\n            if len(live) < len(mine):", "dry_run"),
    # worktrees
    ("a dirty worktree is removed", D,
     "        if dc.git([\"status\", \"--porcelain\", \"--untracked-files=normal\"], cwd=w.path, check=False):",
     "        if False:", "worktrees"),
    ("untracked files do not count as dirty", D,
     '"--untracked-files=normal"], cwd=w.path', '"--untracked-files=no"], cwd=w.path', "worktrees"),
    ("unpushed commits do not keep a worktree", D,
     "    if tip is not None and not local_tip_ok(ctx, tip, v):", "    if False:", "worktrees"),
    ("any commit counts as pushed", D,
     "    return bool(p.stdout.strip())", "    return True", "worktrees"),
    ("a detached worktree is swept along with a finished branch", D,
     "mine = [w for w in trees if w.branch == branch]", "mine = [w for w in trees if w.branch == branch or w.branch is None]",
     "worktrees"),
    ("a locked worktree is removed without --force --force", D,
     '(["--force", "--force"] if w.locked else [])', "[]", "worktrees"),
    ("the main working tree is not protected", D,
     "        if w.main:\n            return", "        if False:\n            return", "worktrees"),
    ("the working tree the script runs in is not protected", D,
     "        if same_path(w.path, ctx.root):\n            return", "        if False:\n            return", "worktrees"),
    ("worktree prune never runs at the end", D, "    if do_local and not ctx.dry:\n        ctx.git([\"worktree\", \"prune\"])",
     "    if False:\n        pass", "worktrees"),
    ("worktree prune runs in --dry-run", D, "    if do_local and not ctx.dry:\n        ctx.git([\"worktree\", \"prune\"])",
     "    if do_local:\n        ctx.git([\"worktree\", \"prune\"])", "worktrees"),
    ("a vanished worktree blocks deleting its branch", D, "            if len(live) < len(mine):", "            if False:", "worktrees"),
    ("no gh: an upstream-gone branch is deleted", D,
     "    if upstream_gone(ctx, branch):\n        return Verdict(False, NEEDS_GH, cannot_classify=True, needs_gh=True)",
     "    if upstream_gone(ctx, branch):\n        return Verdict(True, \"upstream gone\")", "local_without_gh"),
    ("no gh: the needs-gh row deletes after all", D,
     '        if v.needs_gh:\n            row.status, row.detail = "would delete", NEEDS_GH  # listed, never done\n            continue\n',
     '        if v.needs_gh:\n            v = Verdict(True, "upstream gone")\n', "local_without_gh"),
    ("no gh: the needs-gh row is dropped", D,
     '        if v.needs_gh:\n            row.status, row.detail = "would delete", NEEDS_GH  # listed, never done\n            continue\n',
     "", "local_without_gh"),
    ("no gh: every local branch needs gh", D,
     "    if upstream_gone(ctx, branch):\n        return Verdict(False, NEEDS_GH",
     "    if True:\n        return Verdict(False, NEEDS_GH", "local_without_gh"),
    ("a failing gh does not fall back to the upstream check", D,
     "        if not v.cannot_classify:\n            return v\n", "        return v\n", "local_without_gh"),
    ("a working gh no longer decides in --local", D,
     "        if not v.cannot_classify:\n            return v\n", "        if False:\n            return v\n", "local_without_gh"),
    ("the needs-gh row loses its wording", D,
     '            elif r.detail == NEEDS_GH:\n                text = "%s (%s)" % (r.status, r.detail)\n',
     "", "local_without_gh"),
    ("no gh: upstream-gone is never true", D,
     'return merge.removeprefix("refs/heads/") not in ctx.remote_heads', "return False", "local_without_gh"),
    # scaffolding branches and push-check folders
    ("a scaffolding branch with a commit is removed", D, "    if int(p.stdout.strip()) > 0:", "    if int(p.stdout.strip()) > 99:", "scaffolding"),
    ("a scaffolding branch whose name is on the remote is removed", D,
     "branch in ctx.remote_heads or branch in ctx.result_refs:", "False:", "scaffolding"),
    ("scaffolding branches need gh", D,
     '    if not (v.cannot_classify or v.reason == "no pull request"):', '    if not v.reason == "no pull request":', "scaffolding"),
    ("scaffolding branches are compared with the local default branch", D,
     '"refs/remotes/%s..refs/heads/%s" % (base, branch)', '"refs/heads/%s..refs/heads/%s" % (ctx.default, branch)', "scaffolding"),
    ("the rule also finishes a branch whose pull request was closed", D,
     'or v.reason == "no pull request"):', 'or v.reason.startswith("pull requests closed") or v.reason == "no pull request"):', "scaffolding"),
    ("a live push-check folder is swept", D, "        if pid_alive(int(suffix)):", "        if False:", "push_check_sweep"),
    ("--dry-run sweeps push-check folders", D, '        if ctx.dry:\n            row.status = "would delete"',
     '        if False:\n            row.status = "would delete"', "push_check_sweep"),
    ("the sweep deletes link targets", D, "        stuck = [lk for lk in links if not fg.remove_link(lk)]\n",
     "        for lk in links:\n            shutil.rmtree(os.path.realpath(lk), ignore_errors=True)\n"
     "        stuck = [lk for lk in links if not fg.remove_link(lk)]\n", "push_check_sweep"),
    ("the sweep leaves the folder git forgot", D, "        if entry.is_dir():\n            fg.remove_worktree",
     "        if False:\n            fg.remove_worktree", "push_check_sweep"),
    ("the sweep never runs", D, "    if do_local:\n        rows += sweep_push_check(ctx)",
     "    if False:\n        rows += sweep_push_check(ctx)", "push_check_sweep"),
    ("--remote-only sweeps push-check folders", D, "    if do_local:\n        rows += sweep_push_check(ctx)",
     "    if True:\n        rows += sweep_push_check(ctx)", "push_check_sweep"),
    ("a folder not named <sha>-<pid> is swept", D, "        if not suffix.isdigit():", "        if False:", "push_check_sweep"),
    # join.py
    ("join never runs cleanup.py", "scripts/delivery/join.py",
     'parent / "cleanup.py"', 'parent / "nocleanup.py"', "join_cleanup"),
    ("join stops when cleanup.py fails", "scripts/delivery/join.py",
     'dc.eprint("join: cleanup.py --local exited %d; going on" % cleaned)', "return cleaned", "join_cleanup"),
]

SCENARIOS = {
    "classify": sc_classify,
    "gh_failure": sc_gh_failure,
    "default_branch": sc_default_branch,
    "failed_deletion": sc_failed_deletion,
    "pr": sc_pr,
    "modes": sc_modes,
    "dry_run": sc_dry_run,
    "worktrees": sc_worktrees,
    "local_without_gh": sc_local_without_gh,
    "scaffolding": sc_scaffolding,
    "push_check_sweep": sc_push_check_sweep,
    "join_cleanup": sc_join_cleanup,
    "workflow": sc_workflow,
    "assets": sc_assets,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-mutants", action="store_true", help="skip the mutation pass")
    ap.add_argument("-k", metavar="SUBSTRING", help="run only scenarios/mutants whose name contains it")
    args = ap.parse_args()

    fails = total = 0
    for name, fn in SCENARIOS.items():
        if args.k and args.k not in name:
            continue
        t = T(name)
        try:
            fn(t, SHARED)
        except Exception:  # noqa: BLE001 - a crash is a failed scenario, with the trace
            t.check("scenario ran to the end", False, traceback.format_exc())
        total += t.total
        fails += len(t.failures)

    if not args.no_mutants:
        print("\n--- mutation pass: break one rule in a copy; the scenario for it must fail ---")
        for label, rel, old, new, scenario in MUTANTS:
            if args.k and args.k not in scenario and args.k not in label:
                continue
            shared = tdg.mutated_shared(rel, old, new)
            total += 1
            if shared is None:
                fails += 1
                print("FAIL  mutant '%s': the text to mutate is not (uniquely) in %s; update the test" % (label, rel))
                continue
            t = T(scenario, quiet=True)
            crashed = False
            try:
                SCENARIOS[scenario](t, shared)
            except Exception:  # noqa: BLE001
                crashed = True
            caught = bool(t.failures) or crashed
            print("%s  mutant '%s': %s" % (
                "PASS" if caught else "FAIL", label,
                ("caught by %d check(s)%s" % (len(t.failures), " + a crash" if crashed else "")) if caught
                else "NOT CAUGHT; scenario '%s' cannot fail on this rule" % scenario))
            fails += not caught

    print("\n%d checks, %d failed" % (total, fails))
    for tmp in (_TMP, tdg._TMP_ROOT):
        try:
            tdg.rmtree(tmp)
        except OSError:
            pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
