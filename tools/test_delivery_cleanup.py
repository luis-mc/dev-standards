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
        dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep)
                if d and not any((Path(d) / n).exists() for n in ("gh", "gh.exe", "gh.cmd"))]
        path = os.pathsep.join(([str(self.dir)] if with_gh else []) + dirs)
        return {"PATH": path, "GH_STUB_FIXTURE": str(self.fixture), "GH_STUB_LOG": str(self.log), "PYTHONUTF8": "1"}

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x]


# --------------------------------------------------------------------------
# a throwaway repository
# --------------------------------------------------------------------------

DELIVERY_FILES = ["delivery_common.py", "cleanup.py"]


class World:
    def __init__(self, shared: Path = SHARED):
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
        (d / "gate.json").write_text(json.dumps(GATE_JSON), encoding="utf-8")
        self.write(".gitignore", ".claude/worktrees/\n.delivery/\n__pycache__/\n")
        self.write("README.md", "hello\n")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "init")
        self.g("push", "-q", "-u", "origin", "main")
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
    s.pr("main", "MERGED", w.tip("main"), base="release")    # nonsense about the default branch must not matter
    s.fx["errors"].append("head:feat/error")
    s.save()
    # feat/later got a commit after its pull request was merged
    w.g("checkout", "-q", "feat/later")
    w.commit("after the merge")
    w.g("push", "-q", "origin", "feat/later")
    w.g("checkout", "-q", "main")

    r, rows = w.rows("--remote-only")
    t.eq("exit 0 although branches were kept", r.code, 0)
    for b in ("feat/a", "integ", "feat/d1"):
        t.eq("finished (merged pull request): %s" % b, status(rows, b), "deleted")
    t.eq("finished (b): closed draft contained in a finished integration branch", status(rows, "feat/d2"), "deleted")
    t.check("an open pull request keeps the branch, even with an older merged one",
            is_kept(rows, "feat/open", "open pull request"), status(rows, "feat/open"))
    t.check("a pull request closed without merging keeps the branch",
            is_kept(rows, "feat/closed", "closed without merging"), status(rows, "feat/closed"))
    t.check("a closed draft whose commits are not in the integration branch is kept",
            is_kept(rows, "feat/stray", "closed without merging"), status(rows, "feat/stray"))
    t.check("a branch with no pull request is kept", is_kept(rows, "feat/nopr", "no pull request"), status(rows, "feat/nopr"))
    t.check("commits pushed after the merge keep the branch",
            is_kept(rows, "feat/later", "after the merged"), status(rows, "feat/later"))
    t.check("an error from gh keeps the branch", is_kept(rows, "feat/error", "cannot classify"), status(rows, "feat/error"))
    t.check("the default branch gets no row", "main" not in rows, str(sorted(rows)))
    t.eq("remote: only finished branches are gone",
         w.remote_heads(), {"main", "feat/open", "feat/closed", "feat/nopr", "feat/later", "feat/stray", "feat/error"})
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
    t.eq("gh down: exit 0 (nothing decided is not a failure)", r.code, 0)
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
    w = World(shared)
    w.stub.pr("main", "MERGED", w.tip("main"), base="release")
    w.stub.pr("main", "MERGED", w.tip("main"), base="staging")
    for flags in ([], ["--remote-only"], ["--local"]):
        r, rows = w.rows(*flags)
        t.eq("%s: exit 0" % (flags or "default"), r.code, 0)
        t.check("%s: the default branch is never a candidate" % (flags or "default"), "main" not in rows, str(sorted(rows)))
        t.check("%s: main still on the remote and local" % (flags or "default"),
                "main" in w.remote_heads() and "main" in w.local_branches())
    # train of a pull request whose head is the default branch itself
    n = w.stub.pr("main", "MERGED", w.tip("main"), base="main")
    r, rows = w.rows("--pr", str(n))
    t.check("--pr with the default branch as head: nothing deleted", "main" in w.remote_heads() and "main" not in rows)


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
    t.eq("a deletion the remote refuses: exit 1", r.code, 1)
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
    t.eq("--pr of a pull request that is not merged: exit 2", r.code, 2)
    t.has("... says why", r.text, "not merged")
    r = w.cleanup("--pr", "9")
    t.eq("--pr of a pull request merged into an integration branch: exit 2", r.code, 2)
    t.has("... says it is not the default branch", r.text, "default branch")
    r = w.cleanup("--pr", "999")
    t.eq("--pr of an unknown pull request: exit 2", r.code, 2)
    t.eq("refusals removed nothing", w.snapshot(), before)

    r, rows = w.rows("--remote-only", "--pr", str(n))
    t.eq("--pr N (merged into the default branch): exit 0", r.code, 0)
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
    t.eq("--local with --remote-only: exit 2", r.code, 2)

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
    t.eq("--dry-run: exit 0", r.code, 0)
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
    t.eq("exit 0 with worktrees kept", r.code, 0)
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
    w2.g("checkout", "-q", "feat/main-tree")
    r, rows = w2.rows("--local")
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


def sc_local_without_gh(t: T, shared: Path) -> None:
    w = World(shared)
    w.branch("feat/gone")      # merged and deleted on the remote: upstream gone
    w.branch("feat/live")      # upstream still there
    w.branch("feat/local", push=False)  # never pushed
    w.worktree("gone", "feat/gone")
    w.g("push", "-q", "origin", "--delete", "feat/gone")
    before = w.snapshot()
    r, rows = w.rows("--local", gh=False)
    t.eq("no gh, --local: exit 0", r.code, 0)
    t.eq("no gh: a branch whose upstream is gone is finished", status(rows, "feat/gone"), "deleted")
    t.eq("... branch and worktree removed", ("feat/gone" in w.local_branches(), "gone" in w.worktrees()), (False, False))
    t.check("no gh: a branch whose upstream exists is kept", is_kept(rows, "feat/live"), status(rows, "feat/live"))
    t.check("no gh: a branch that was never pushed is kept", is_kept(rows, "feat/local"), status(rows, "feat/local"))
    t.eq("no gh: those branches are untouched", {"feat/live", "feat/local"} <= w.local_branches(), True)

    w2 = World(shared)
    sha = w2.branch("feat/a")
    w2.stub.pr("feat/a", "MERGED", sha)
    before = w2.snapshot()
    r, rows = w2.rows(gh=False)
    t.eq("no gh, remote mode: nothing can be classified, nothing is removed", w2.snapshot(), before)
    t.check("... and the branch is listed as kept", is_kept(rows, "feat/a"), status(rows, "feat/a"))


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
    t.eq("join with a finished local branch: exit 0", r.code, 0)
    t.eq("... cleanup.py --local ran before the join: worktree and branch gone",
         (wt.exists(), "agent/old" in box.g("branch", "--format=%(refname:short)").split()), (False, False))
    t.check("... and it ran before the first fetch (gh was asked before any merge)", len(stub.calls()) > 0)
    t.eq("... the join itself still happened", box.g("log", "--merges", "--format=%s", "integ").splitlines(), ["Join feat/a"])

    # best effort: a failing cleanup.py never stops the join
    box = join_box(shared, "import sys\nprint('cleanup exploded', file=sys.stderr)\nsys.exit(2)\n")
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = box.script("join.py", "--into", "integ", "feat/a")
    t.eq("cleanup.py exits 2: the join still succeeds", r.code, 0)
    t.has("... and says it went on", r.text, "going on")
    t.eq("... and joined", box.g("log", "--merges", "--format=%s", "integ").splitlines(), ["Join feat/a"])

    # nothing to clean (no gh): a real cleanup.py failing to classify never stops it either
    box = join_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = box.script("join.py", "--into", "integ", "feat/a", env=Stub().env(with_gh=False))
    t.eq("join without gh: exit 0", r.code, 0)


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
    t.check("cleanup.py has a python3 shebang and no CRLF", src.startswith(b"#!/usr/bin/env python3") and b"\r\n" not in src)
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
     'return Verdict(False, "cannot classify (%s)" % exc)', 'return Verdict(True, "cannot classify (%s)" % exc)',
     "gh_failure"),
    ("commits pushed after the merge are ignored", D,
     "if do_remote and tip and not v.unverifiable and not contained(ctx, tip, v.safe):", "if False:", "classify"),
    ("the default branch is not protected", D,
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
    ("--dry-run deletes local branches", D, "        if not ctx.dry:\n            p = ctx.git([\"branch\", \"-D\"",
     "        if True:\n            p = ctx.git([\"branch\", \"-D\"", "dry_run"),
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
    ("a vanished worktree is not pruned", D, "    if do_local and not ctx.dry:\n        ctx.git([\"worktree\", \"prune\"])",
     "    if False:\n        pass", "worktrees"),
    ("no gh: every local branch is finished", D,
     "    if gone:\n        return Verdict(True", "    if True:\n        return Verdict(True", "local_without_gh"),
    ("no gh: upstream-gone is never true", D,
     'return merge.removeprefix("refs/heads/") not in ctx.remote_heads', "return False", "local_without_gh"),
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
