#!/usr/bin/env python3
"""Remove what a merged train leaves behind (STACKSPEC 13.6, last bullet).

    cleanup.py [--pr N] [--remote origin] [--local] [--remote-only] [--dry-run] [--json] [--repo OWNER/NAME]

A branch is FINISHED when it is not the default branch, has no open pull
request, and either (a) a pull request with it as head is merged, or (b) it is
the head of a pull request closed without merging whose base is a finished
integration branch and whose commits that branch contained (GitHub closes a
draft when its base branch is deleted). Everything else is KEPT and listed, and
so is any branch that `gh` cannot classify: an error never deletes anything.
Branches are classified by pull-request state, never by ancestry with the default
branch: an integration branch is squash-merged, so its commits are not ancestors
of the default branch.

For each finished branch:
  remote (not with --local)       delete the branch and refs/gate-results/<branch>
  local (not with --remote-only)  remove every worktree checked out on it, then
                                  delete the local branch, then `git worktree prune`
A worktree is kept (and so is its branch) when it has uncommitted changes, when
its commits are not on the remote or in the merged pull request, or when it is
the main working tree or the one this script runs in. A locked worktree (Claude
Code leaves its agent worktrees locked) is removed only after those checks.
Detached worktrees and the default branch are never touched.

--pr N considers only the train of that merged pull request (its head branch and
every branch whose pull request had that head as base); N must be merged into the
default branch, or the script exits 2. Without it, every branch on the remote
(and every local branch). --local treats local branches and worktrees only; with
no `gh` installed a local branch is finished when its upstream is gone from the
remote. --dry-run changes nothing except what a `git fetch` brings in.

One row per branch: `deleted`, `would delete`, `kept: <reason>` or `failed: ...`.
Exit: 0 it ran (kept branches are not a failure), 1 a deletion failed, 2 usage,
no repository, or it could not decide.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc

PR_FIELDS = "number,state,baseRefName,headRefOid,mergedAt"
MAX_PRS = "200"


class GhError(Exception):
    pass


# --------------------------------------------------------------------------
# gh
# --------------------------------------------------------------------------

def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_json(args: list[str], repo: str | None) -> object:
    gh = shutil.which("gh")
    if gh is None:
        raise GhError("gh is not installed")
    cmd = [gh, *args] + (["--repo", repo] if repo else [])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhError("could not run gh: %s" % exc) from exc
    if proc.returncode != 0:
        raise GhError("gh %s failed (%d): %s" % (" ".join(args[:2]), proc.returncode, (proc.stderr or proc.stdout).strip()[:200]))
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GhError("gh %s returned invalid JSON: %s" % (" ".join(args[:2]), exc)) from exc


def pr_list(repo: str | None, *, head: str | None = None, base: str | None = None) -> list[dict]:
    fields = PR_FIELDS + (",headRefName" if base else "")
    args = ["pr", "list", "--state", "all", "--limit", MAX_PRS, "--json", fields]
    args += ["--head", head] if head else ["--base", base]
    data = gh_json(args, repo)
    if not isinstance(data, list):
        raise GhError("gh pr list did not return a list")
    return data


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

@dataclass
class Verdict:
    finished: bool
    reason: str = ""
    safe: list[str] = field(default_factory=list)  # merged head shas: a tip at or below one is not lost
    unverifiable: bool = False  # finished by "upstream gone": commits cannot be compared


@dataclass
class Worktree:
    path: str
    branch: str | None  # short name; None when detached or bare
    locked: bool
    prunable: bool
    main: bool


@dataclass
class Row:
    branch: str
    status: str = ""  # deleted | would delete | kept | failed
    detail: str = ""
    removed: list[str] = field(default_factory=list)


class Ctx:
    def __init__(self, root: Path, remote: str, repo: str | None, default: str, protected: set[str], dry: bool):
        self.root, self.remote, self.repo, self.default = root, remote, repo, default
        self.protected, self.dry = protected, dry
        self.verdicts: dict[str, Verdict] = {}
        self.remote_heads: dict[str, str] | None = {}
        self.result_refs: set[str] = set()

    def git(self, args: list[str], **kw):
        return dc.run_git(args, cwd=self.root, check=False, **kw)


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------

def ensure_object(ctx: Ctx, sha: str, number: int | None) -> None:
    """Best effort: a squash-merged pull request's head may be a commit no branch
    holds any more; GitHub keeps it at refs/pull/N/head."""
    if sha and dc.rev(sha, ctx.root) is None and number:
        ctx.git(["fetch", "--quiet", ctx.remote, "refs/pull/%d/head" % number])


def contained(ctx: Ctx, tip: str, safe: list[str]) -> bool:
    return any(tip == s or dc.is_ancestor(tip, s, ctx.root) for s in safe)


def assess(ctx: Ctx, branch: str, depth: int = 0) -> Verdict:
    if branch in ctx.verdicts:
        return ctx.verdicts[branch]
    v = _assess(ctx, branch, depth)
    ctx.verdicts[branch] = v
    return v


def _assess(ctx: Ctx, branch: str, depth: int) -> Verdict:
    if branch in ctx.protected:
        return Verdict(False, "default branch")
    try:
        prs = pr_list(ctx.repo, head=branch)
    except GhError as exc:
        return Verdict(False, "cannot classify (%s)" % exc)
    if not prs:
        return Verdict(False, "no pull request")
    opened = [p for p in prs if p.get("state") == "OPEN"]
    if opened:
        return Verdict(False, "open pull request #%s" % opened[0].get("number"))
    merged = [p for p in prs if p.get("state") == "MERGED"]
    if merged:
        for p in merged:
            ensure_object(ctx, p.get("headRefOid") or "", p.get("number"))
        return Verdict(True, "pull request #%s merged" % merged[0].get("number"),
                       [p["headRefOid"] for p in merged if p.get("headRefOid")])
    if depth < 5:  # (b): closed because its integration branch was merged and deleted
        for p in prs:
            base, sha = p.get("baseRefName") or "", p.get("headRefOid") or ""
            if not base or base == branch or base in ctx.protected or not sha:
                continue
            bv = assess(ctx, base, depth + 1)
            if not bv.finished:
                continue
            ensure_object(ctx, sha, p.get("number"))
            targets = list(bv.safe)
            tip = (ctx.remote_heads or {}).get(base)
            if tip:
                targets.append(tip)
            if contained(ctx, sha, targets):
                return Verdict(True, "pull request #%s closed into finished %s" % (p.get("number"), base), [sha])
    return Verdict(False, "pull requests closed without merging (%s)"
                   % ", ".join("#%s" % p.get("number") for p in prs))


def upstream_gone(ctx: Ctx, branch: str) -> bool | None:
    """Has `branch` an upstream that is no longer on the remote? None: cannot tell."""
    merge = dc.git(["config", "branch.%s.merge" % branch], cwd=ctx.root, check=False)
    remote = dc.git(["config", "branch.%s.remote" % branch], cwd=ctx.root, check=False)
    if not merge or remote != ctx.remote or ctx.remote_heads is None:
        return None if ctx.remote_heads is None else False
    return merge.removeprefix("refs/heads/") not in ctx.remote_heads


def assess_local(ctx: Ctx, branch: str) -> Verdict:
    if gh_available():
        return assess(ctx, branch)
    if branch in ctx.protected:
        return Verdict(False, "default branch")
    gone = upstream_gone(ctx, branch)
    if gone:
        return Verdict(True, "upstream gone", unverifiable=True)
    return Verdict(False, "cannot classify (gh is not installed) and its upstream is not gone")


# --------------------------------------------------------------------------
# remote and local actions
# --------------------------------------------------------------------------

def push_delete(ctx: Ctx, ref: str) -> str | None:
    """Delete one remote ref. None on success, else the error."""
    p = ctx.git(["push", "--quiet", "--no-verify", ctx.remote, "--delete", ref])
    if p.returncode == 0 or "remote ref does not exist" in p.stderr:
        return None
    return p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "push failed"


def list_worktrees(ctx: Ctx) -> list[Worktree]:
    out = dc.git(["worktree", "list", "--porcelain"], cwd=ctx.root, check=False)
    trees: list[Worktree] = []
    for block in out.split("\n\n"):
        info: dict[str, str] = {}
        for line in block.splitlines():
            key, _, val = line.partition(" ")
            info[key] = val
        if "worktree" not in info:
            continue
        ref = info.get("branch", "")
        trees.append(Worktree(
            path=info["worktree"],
            branch=ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else None,
            locked="locked" in info,
            prunable="prunable" in info,
            main=not trees,
        ))
    return trees


def same_path(a: str, b: str | Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(str(b)))


def local_tip_ok(ctx: Ctx, tip: str, v: Verdict) -> bool:
    if v.unverifiable or contained(ctx, tip, v.safe):
        return True
    p = ctx.git(["for-each-ref", "--contains", tip, "--count=1", "--format=%(refname)", "refs/remotes/%s/" % ctx.remote])
    return bool(p.stdout.strip())


def clean_local(ctx: Ctx, branch: str, v: Verdict, trees: list[Worktree], row: Row) -> str | None:
    """Remove the worktrees and the local branch. Returns why something was kept."""
    tip = dc.rev("refs/heads/" + branch, ctx.root)
    mine = [w for w in trees if w.branch == branch]
    if tip is None and not mine:
        return None
    if tip is not None and not local_tip_ok(ctx, tip, v):
        return "commits not on the remote or in the merged pull request"
    live = [w for w in mine if not w.prunable]
    for w in live:
        if w.main:
            return "checked out in the main working tree"
        if same_path(w.path, ctx.root):
            return "checked out in the working tree this runs in"
    for w in live:
        if dc.git(["status", "--porcelain", "--untracked-files=normal"], cwd=w.path, check=False):
            return "worktree %s has uncommitted changes" % dc.posix(w.path)
    for w in live:
        if ctx.dry:
            row.removed.append("worktree %s" % dc.posix(w.path))
            continue
        cmd = ["worktree", "remove"] + (["--force", "--force"] if w.locked else []) + [w.path]
        p = ctx.git(cmd)
        if p.returncode != 0:
            raise RuntimeError("git worktree remove %s: %s" % (dc.posix(w.path), p.stderr.strip()))
        row.removed.append("worktree %s" % dc.posix(w.path))
    if tip is not None:
        if not ctx.dry:
            if len(live) < len(mine):  # a worktree whose directory vanished still holds the branch
                ctx.git(["worktree", "prune"])
            p = ctx.git(["branch", "-D", branch])
            if p.returncode != 0:
                raise RuntimeError("git branch -D %s: %s" % (branch, p.stderr.strip()))
        row.removed.append("local branch")
    return None


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def default_branch(root: Path, remote: str) -> str:
    try:
        return dc.load_gate(root)["default_branch"]
    except dc.DeliveryError:
        ref = dc.git(["symbolic-ref", "--quiet", "--short", "refs/remotes/%s/HEAD" % remote], cwd=root, check=False)
        return ref.split("/", 1)[1] if "/" in ref else "main"


def ls_remote(ctx: Ctx) -> None:
    p = ctx.git(["ls-remote", ctx.remote, "refs/heads/*", "refs/gate-results/*"])
    if p.returncode != 0:
        ctx.remote_heads = None
        return
    ctx.remote_heads = {}
    for line in p.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            ctx.remote_heads[ref[len("refs/heads/"):]] = sha
        elif ref.startswith(dc.RESULT_REF_PREFIX):
            ctx.result_refs.add(ref[len(dc.RESULT_REF_PREFIX):])
    sym = ctx.git(["ls-remote", "--symref", ctx.remote, "HEAD"])
    for line in sym.stdout.splitlines():
        if line.startswith("ref: "):
            ctx.protected.add(line.split()[1].removeprefix("refs/heads/"))


def train_of(ctx: Ctx, number: int) -> list[str]:
    """The merged pull request N's head branch and every branch whose pull request
    had one of the train's branches as base. Refuses unless N is merged into the default branch."""
    try:
        pr = gh_json(["pr", "view", str(number), "--json", "number,state,headRefName,baseRefName"], ctx.repo)
    except GhError as exc:
        raise dc.DeliveryError("cannot read pull request #%d: %s" % (number, exc))
    if not isinstance(pr, dict) or pr.get("state") != "MERGED":
        raise dc.DeliveryError("pull request #%d is not merged; nothing to clean up" % number)
    if pr.get("baseRefName") != ctx.default:
        raise dc.DeliveryError("pull request #%d was merged into '%s', not the default branch '%s'; "
                               "a train is removed only when its ready pull request lands on the default branch"
                               % (number, pr.get("baseRefName"), ctx.default))
    train, queue = [], [pr["headRefName"]]
    while queue:
        name = queue.pop(0)
        if name in train:
            continue
        train.append(name)
        try:
            children = pr_list(ctx.repo, base=name)
        except GhError as exc:
            raise dc.DeliveryError("cannot list the pull requests into '%s': %s" % (name, exc))
        queue += [c["headRefName"] for c in children if c.get("headRefName")]
    return [b for b in train if b not in ctx.protected]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cleanup.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--pr", type=int, metavar="N", help="only the train of this merged pull request")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--local", action="store_true", help="local branches and worktrees only")
    ap.add_argument("--remote-only", action="store_true", help="the remote only (what CI runs)")
    ap.add_argument("--dry-run", action="store_true", help="say what would be removed; remove nothing")
    ap.add_argument("--json", action="store_true", help="print the rows as JSON")
    ap.add_argument("--repo", metavar="OWNER/NAME", help="repository for gh (default: the current one)")
    args = ap.parse_args(argv)
    if args.local and args.remote_only:
        raise dc.DeliveryError("--local and --remote-only exclude each other")

    root = dc.repo_root()
    if args.remote not in dc.remotes(root):
        raise dc.DeliveryError("remote '%s' not found" % args.remote)
    do_remote, do_local = not args.local, not args.remote_only
    default = default_branch(root, args.remote)
    ctx = Ctx(root, args.remote, args.repo, default, {default}, args.dry_run)

    fetch = ["fetch", "--quiet"] + ([] if args.dry_run else ["--prune"]) + [args.remote]
    if ctx.git(fetch).returncode != 0:
        dc.eprint("cleanup: warning: git fetch failed; deciding from what is local")
    ls_remote(ctx)
    if ctx.remote_heads is None and do_remote:
        raise dc.DeliveryError("cannot list the branches on remote '%s'" % args.remote)
    heads = ctx.remote_heads or {}

    local_branches = [b for b in dc.git(["for-each-ref", "--format=%(refname:short)", "refs/heads/"], cwd=root).splitlines() if b]
    if args.pr is not None:
        candidates = train_of(ctx, args.pr)
    else:
        names = set()
        if do_remote:
            names |= set(heads) | ctx.result_refs
        if do_local:
            names |= set(local_branches)
        candidates = sorted(names - ctx.protected)

    trees = list_worktrees(ctx) if do_local else []
    rows: list[Row] = []
    for branch in candidates:
        row = Row(branch)
        rows.append(row)
        local_here = do_local and (branch in local_branches or any(w.branch == branch for w in trees))
        remote_here = do_remote and (branch in heads or branch in ctx.result_refs)
        # a branch only a local-mode run can see may be classified without gh
        v = assess_local(ctx, branch) if (args.local or (local_here and not remote_here)) else assess(ctx, branch)
        if not v.finished:
            row.status, row.detail = "kept", v.reason
            continue
        tip = heads.get(branch)
        if do_remote and tip and not v.unverifiable and not contained(ctx, tip, v.safe):
            row.status, row.detail = "kept", "commits on the remote after the merged pull request"
            continue
        verb = "would delete" if ctx.dry else "deleted"
        try:
            if do_remote:
                for ref, here in (("refs/heads/" + branch, branch in heads),
                                  (dc.RESULT_REF_PREFIX + branch, branch in ctx.result_refs)):
                    if not here:
                        continue
                    if not ctx.dry:
                        err = push_delete(ctx, ref)
                        if err:
                            raise RuntimeError("could not delete %s: %s" % (ref, err))
                    row.removed.append("remote branch" if ref.startswith("refs/heads/") else "gate-result ref")
            if do_local:
                why = clean_local(ctx, branch, v, trees, row)
                if why:
                    row.status, row.detail = "kept", why
                    continue
            row.status = verb
            if not row.removed:
                row.detail = "already gone"
        except RuntimeError as exc:
            row.status, row.detail = "failed", str(exc)

    if do_local and not ctx.dry:
        ctx.git(["worktree", "prune"])

    if args.json:
        print(json.dumps([{"branch": r.branch, "status": r.status, "detail": r.detail, "removed": r.removed}
                          for r in rows], indent=2))
    else:
        for r in rows:
            done = "removed: " + ", ".join(r.removed) if r.removed else ""
            if r.status in ("kept", "failed"):
                text = "%s: %s" % (r.status, r.detail) + ("  [%s]" % done if done else "")
            else:
                text = r.status + "  (%s)" % (done[len("removed: "):] if done else r.detail)
            print("%s  %s" % (r.branch, text))
        if not rows:
            print("cleanup: nothing to consider")
    return dc.EXIT_FAIL if any(r.status == "failed" for r in rows) else dc.EXIT_OK


if __name__ == "__main__":
    dc.main_guard(main)
