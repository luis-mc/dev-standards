#!/usr/bin/env python3
"""The seconds-long checks of the branch gate, for the pre-push hook (STACKSPEC 13.5).

    fast_guards.py [--base-ref REF] [--commit SHA] [--timeout-minutes N]

Runs the gate.json steps marked "pre_push": true (the guard tests, the secret
scan, and typecheck + lint of the touched packages, which skip when no package changed), continuing past a failure so one run reports everything. Each step has a
time limit (5 minutes); one over it is killed with everything it started and
fails. A failed step is reported the way the branch gate reports one: the
"FAIL <step>: <reason> (exit N, Ns) - log: <path>" line and the last 40 lines of
its output, so a blocked push says which check failed and why. Step logs are in
.delivery/logs/pre-push/ of the checkout the script is run from. Then it runs the
gate.json "always_on_guards" (DL307): each {name, command, inputs: [globs]} whose
inputs match a file changed since the base, one at a time; the others are skipped
with one line each, and "**" always runs. A failed guard fails the run with its
name and output tail. Never writes or
publishes a gate result; the pre-push hook calls it once per pushed ref.

--commit SHA names the commit to check (the hook passes the one being pushed).
When it is not the checked-out commit, that commit is checked out in a temporary
detached worktree under .delivery/push-check/<sha12>-<pid>, the steps run there,
and the worktree is always removed afterwards, also on failure or interruption.
It shares this repository's object store and has no install of its own: every
node_modules found in this checkout is linked into it at the same relative path
(a symlink, or a junction on Windows; never a copy), and when this checkout has a
target/ directory, CARGO_TARGET_DIR points at it. Without --commit, or with the
checked-out commit, the steps run in place.

Exit: 0 all passed, 1 a step failed or timed out, 2 usage/configuration error.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc

PUSH_CHECK_DIR = ".delivery/push-check"
LINKED_DIRS = ("node_modules",)  # dependency directories linked into the worktree, never copied
_NOT_WALKED = {".git", ".delivery", "target"}  # not searched for dependency directories
_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR")


def find_dependency_dirs(root: Path) -> list[str]:
    """Paths (POSIX, relative to `root`) of every dependency directory in the
    checkout. Nested checkouts and worktrees (a directory with its own .git) are
    not searched, and nothing is searched inside a dependency directory."""
    found: list[str] = []
    for dirpath, dirnames, _files in os.walk(root):
        here = Path(dirpath)
        keep = []
        for name in sorted(dirnames):
            if name in LINKED_DIRS:
                found.append(dc.posix((here / name).relative_to(root)))
            elif name not in _NOT_WALKED and not (here / name / ".git").exists():
                keep.append(name)
        dirnames[:] = keep
    return found


def is_link(path: Path) -> bool:
    """A symlink, or a Windows junction (Python 3.11 reports a junction as neither
    a link nor a mount)."""
    if os.path.islink(path):
        return True
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def make_link(link: Path, target: Path) -> bool:
    """A directory link at `link` to `target`: a symlink, or a junction on Windows
    (which needs no privilege). True when it was made."""
    try:
        if os.name == "nt":
            p = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False
            )
            return p.returncode == 0 and is_link(link)
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        return False


def remove_link(link: Path) -> bool:
    """Remove the link itself, never what it points to. True when nothing of ours
    is left at `link` (also when a step already replaced the link with a directory
    of its own)."""
    if not is_link(link):
        return True
    try:
        if os.path.islink(link):
            os.unlink(link)
        else:
            os.rmdir(link)  # a junction: this removes the junction, not its target
    except OSError:
        pass
    return not os.path.lexists(link)


def remove_worktree(root: Path, path: Path, links: list[Path]) -> None:
    """Take the temporary worktree away. The links come off first: if one cannot be
    removed, the worktree stays (and says so) rather than risk the dependencies
    it points to."""
    stuck = [lk for lk in links if not remove_link(lk)]
    if stuck:
        dc.eprint("fast_guards: warning: could not remove the link %s; left %s in place" % (stuck[0], path))
        return
    dc.run_git(["worktree", "remove", "--force", str(path)], cwd=root, check=False)
    for _ in range(5):
        if not path.exists():
            break
        # git could not (a killed step may still hold a file open on Windows): remove it
        # ourselves, now that no link of ours is left inside it.
        shutil.rmtree(path, ignore_errors=True)
        if path.exists():
            time.sleep(0.4)
    dc.run_git(["worktree", "prune"], cwd=root, check=False)
    if path.exists():
        dc.eprint("fast_guards: warning: could not remove %s" % path)
    try:
        path.parent.rmdir()  # only when empty: another push may be checking a commit too
    except OSError:
        pass


def _interrupt(_signum, _frame):
    raise KeyboardInterrupt


def run_in_push_worktree(root: Path, commit: str, args: argparse.Namespace) -> int:
    path = root / PUSH_CHECK_DIR / ("%s-%d" % (commit[:12], os.getpid()))
    links: list[Path] = []
    saved_env = {k: os.environ.get(k) for k in (*_GIT_ENV, "CARGO_TARGET_DIR")}
    # A terminated hook cleans up too (Ctrl-C already raises KeyboardInterrupt).
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _interrupt)
    try:
        for k in _GIT_ENV:  # git may hand a hook the pushing repository's index and directories
            os.environ.pop(k, None)
        path.parent.mkdir(parents=True, exist_ok=True)
        dc.run_git(["worktree", "add", "--detach", str(path), commit], cwd=root)
        for rel in find_dependency_dirs(root):
            dest = path / rel
            if dest.parent.is_dir() and not os.path.lexists(dest):
                if make_link(dest, root / rel):
                    links.append(dest)
                else:
                    dc.eprint("fast_guards: warning: could not link %s into the worktree" % rel)
        if (root / "target").is_dir() and "CARGO_TARGET_DIR" not in os.environ:
            os.environ["CARGO_TARGET_DIR"] = str(root / "target")
        print("fast_guards: checking pushed commit %s in %s" % (commit[:10], dc.posix(path.relative_to(root))),
              flush=True)
        return run_guards(root, path, args)
    finally:
        remove_worktree(root, path, links)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def pushed_file(work: Path, commit: str, name: str) -> str | None:
    """Text of `name` in `commit`, or None when the commit has no such file."""
    r = subprocess.run(["git", "show", "%s:%s" % (commit, name)], cwd=str(work), capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def gitleaks_flags(work: Path, commit: str, tmp: Path) -> str:
    """Flags that make gitleaks read .gitleaksignore and .gitleaks.toml from the
    pushed commit, not from the working tree (DL154, R13.78). A commit with no
    .gitleaksignore gets an empty one, so the working tree's does not apply."""
    ignore = pushed_file(work, commit, ".gitleaksignore")
    f = tmp / "gitleaksignore"
    f.write_text(ignore or "", encoding="utf-8", newline="")
    flags = ' --gitleaks-ignore-path "%s"' % f
    config = pushed_file(work, commit, ".gitleaks.toml")
    if config is not None:
        c = tmp / "gitleaks.toml"
        c.write_text(config, encoding="utf-8", newline="")
        flags += ' --config "%s"' % c
    return flags


def with_pushed_gitleaks(steps: list[dict], work: Path, commit: str, tmp: Path) -> list[dict]:
    out = []
    for s in steps:
        if s["run"].lstrip().startswith("gitleaks "):
            s = dict(s, run=s["run"] + gitleaks_flags(work, commit, tmp))
        out.append(s)
    return out


def run_guards(root: Path, work: Path, args: argparse.Namespace) -> int:
    """Run the pre_push steps with `work` as the checkout (the pushed commit's
    worktree, or `root` itself). Logs are kept under `root`."""
    # An older pushed commit may predate gate.json: the checked-out one then decides.
    cfg = dc.load_gate(work if (work / dc.GATE_JSON_PATH).is_file() else root)
    steps = [s for s in cfg["steps"] if s["pre_push"]]
    if not steps:
        raise dc.DeliveryError("gate.json has no step with \"pre_push\": true")

    ctx = dc.build_context(work, cfg, args.base_ref)
    tmp = Path(tempfile.mkdtemp(prefix="fast-guards-"))
    try:
        steps = with_pushed_gitleaks(steps, work, ctx.head, tmp)
        return _run_steps(root, steps, ctx, args)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def glob_to_regex(pat: str) -> "re.Pattern[str]":
    """A path glob as a regex: `*` and `?` stay inside one directory, `**` crosses
    directories, `**/` also matches no directory."""
    pat = pat.replace("\\", "/")
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out) + r"\Z")


def guard_match(inputs: list[str], files: list[str]) -> str | None:
    """The first changed file one of the globs matches, or None."""
    regexes = [glob_to_regex(g) for g in inputs]
    for f in files:
        if any(r.match(f) for r in regexes):
            return f
    return None


def run_always_on_guards(root: Path, guards: list[dict], ctx, args: argparse.Namespace) -> bool:
    """Run each declared guard whose inputs match a changed file, one at a time
    (DL307). True when all that ran passed. Skipped guards get one line each."""
    ok = True
    for g in guards:
        hit = guard_match(g["inputs"], ctx.files)
        if hit is None:
            print("always-on guard %s: skipped, no changed file matches its inputs" % g["name"], flush=True)
            continue
        print("always-on guard %s: running (%s changed) ..." % (g["name"], hit), flush=True)
        log_rel = "%s/guard-%s.log" % (dc.FAST_LOG_DIR, dc._log_name(g["name"]))
        log_path = root / log_rel
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "wb") as log:
            code, secs, timed_out = dc.run_logged(g["command"], ctx.root, None, log, args.timeout_minutes * 60)
        if code == 0 and not timed_out:
            print("always-on guard %s: pass (%.1fs)" % (g["name"], secs), flush=True)
            continue
        ok = False
        why = "timed out" if timed_out else "exit %d" % code
        print("FAIL always-on guard %s: %s (%.1fs) - log: %s" % (g["name"], why, secs, log_rel), flush=True)
        for line in dc.log_tail(log_path):
            print("    " + line)
    return ok


def _run_steps(root: Path, steps: list[dict], ctx, args: argparse.Namespace) -> int:
    print("fast_guards: head %s, base %s, limit %g min per step" % (ctx.head[:10], ctx.base[:10], args.timeout_minutes))
    entries, _ = dc.execute_steps(
        steps,
        ctx,
        keep_going=True,
        limit_seconds=args.timeout_minutes * 60,
        per_step=True,
        log_dir=dc.FAST_LOG_DIR,
        log_root=root,
    )
    print("\n" + dc.summary_table(entries))
    dc.print_failures(entries, root)
    guards = ctx.cfg.get("always_on_guards") or []
    guards_ok = run_always_on_guards(root, guards, ctx, args) if guards else True
    if dc.overall_pass(entries):
        return dc.EXIT_OK if guards_ok else dc.EXIT_FAIL
    if not any(e["outcome"] != "skip" for e in entries):
        dc.eprint("error: no pre_push step ran, so the guards cannot decide")
    return dc.EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fast_guards.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-ref", help="ref or commit the pushed work is compared with (default "
                                       "origin/<default_branch>); 'auto' picks the remote branch the commit "
                                       "was cut from (nearest fork point)")
    ap.add_argument("--branch", metavar="NAME",
                    help="name of the branch being pushed; --base-ref auto never picks it (default: the checked-out branch)")
    ap.add_argument("--commit", metavar="SHA",
                    help="commit to check (default: the checked-out one); another commit is checked out in a "
                         "temporary worktree under %s/" % PUSH_CHECK_DIR)
    ap.add_argument("--timeout-minutes", type=float, default=dc.FAST_STEP_TIMEOUT_MINUTES, metavar="N",
                    help="limit for each step (default %d)" % dc.FAST_STEP_TIMEOUT_MINUTES)
    args = ap.parse_args(argv)
    if not args.timeout_minutes > 0:
        ap.error("--timeout-minutes must be greater than 0")

    root = dc.repo_root()
    commit = None
    if args.commit:
        commit = dc.rev(args.commit, root)
        if commit is None:
            raise dc.DeliveryError("--commit '%s' is not a commit of this repository" % args.commit)
    if args.base_ref == "auto":
        cfg = dc.load_gate(root)
        args.base_ref = dc.fork_point_base(
            root, commit or "HEAD", cfg["default_branch"], args.branch or dc.current_branch(root)
        )
        print("base: %s (fork point)" % args.base_ref, flush=True)
    if commit is not None:
        if commit != dc.rev("HEAD", root):
            return run_in_push_worktree(root, commit, args)
    return run_guards(root, root, args)


if __name__ == "__main__":
    dc.main_guard(main)
