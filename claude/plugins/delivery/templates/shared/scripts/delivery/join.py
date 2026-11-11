#!/usr/bin/env python3
"""Join gated branches into the integration branch (STACKSPEC 13.6).

    join.py --into INTEGRATION BRANCH [BRANCH ...] [--no-gate] [--ci-gate] [--push] [--remote origin]

Runs `cleanup.py --local` (best effort), fetches, checks out INTEGRATION at its
remote head, and for each BRANCH in order:
requires a trusted, passing gate result (a base older than INTEGRATION's head is
fine), then merges it with `git merge --no-ff -m "Join BRANCH"`. A conflict that
touches only a lockfile is resolved by taking INTEGRATION's version and re-running
gate.json's `setup`; any other conflict aborts that merge only (DL111),
and the join goes on with the next branch: every clean merge is kept, each conflicting branch is
skipped and reported with its files ("conflicting" in .delivery/join-result.json). With --push the clean
merges are pushed; without it they stay committed on the local branch. Exit 3. A partial join skips
docs stripping, the gallery rebuild, the light check and the ready pull request text; they run when the
rest is joined. A gate-result refusal stops at once, keeps the earlier clean merges the same way, and
exits with the refusal's code. After the last merge a light check runs on the
joined head (unless --no-gate; or unless the joined tree equals the tree of a joined
branch head whose gate result is trusted for that head and for the base the gate would use,
in which case it is skipped and the output says so): setup (install from the lockfile), then
the typecheck and lint steps of gate.json for the packages the merges touched, then the fast
guards (the pre_push steps of fast_guards.py). It is never a branch gate and never runs the
tests: the ready pull request's CI is the one full suite, so no result is published and a
fix made after a failed check is not re-gated. gate.json picks the steps ("join": true or
false on a step) and may turn the guards off ("join_guards": false). Each step's time is
printed and written to join-result.json ("quick_check"). Last, runner health (runner_health.py) warns when no online runner carries a label CI needs; it never
blocks. --push then pushes INTEGRATION.

--ci-gate (or "ci_gate": true in gate.json; DELIVERYSPEC DL-81, DL-83) is the light join of urgent work at code
push: a branch whose agent's gate is its branch CI run (agent_ci.py) needs no gate result, so it is joined as
soon as its code is pushed; a branch that does have a gate result is still checked. Without the flag nothing changes.

DOCSPEC R10.3: after the last merge, when the luismc-docs plugin is present (found through $LUISMC_DOCS_WORK, the plugin
cache `~/.claude/plugins/cache/*/luismc-docs/<newest>/scripts/`, or the marketplace checkout), join.py runs
`docs_work.py strip --apply` on the joined head (briefs and reports under docs/work/ never reach the default branch),
commits the removal as "Strip temporary agent docs", and saves each report's summary line to
join-result.json ("docs_summaries") and to .delivery/docs-summaries.md for the ready pull request body. Without the
plugin it says so and goes on.

DL128: when a branch to join already contains an older head of another branch in the same call (stacked), the
join stops that branch with "B is stacked on an older A; prefer B's side for files B rewrote" (git merge-base
--is-ancestor), unless B alone carries A (A's head is already in B). DL129: `--into X` with X missing on the remote
stops with the exact command to create it; `--create` pushes origin/<default> as X and goes on. DL135: a failed
light check whose output has an api-mock "unhandled API call" teardown error is reported as a join-interaction
failure. DL140: before the ready pull request the join runs, when the docs plugin is present, the design-system
review visuals rebuild (design_system.py visuals --apply), docs_index.py build and docs_check.py --strict, and lists
the specs with T2 findings; a missing script is skipped with a note. DL145: when local INTEGRATION is ahead of
origin/INTEGRATION the join builds on it; it refuses when local has commits that are not descendants of
origin/INTEGRATION (they would be lost). Conflicts under docs/work/ resolve by taking either side.

DL225: a branch argument `origin/X` (any configured remote) means X. `--into` may be left out: the
integration branch is then `<first task id>-integration`, the head the ready-PR guard accepts. A new
INTEGRATION (neither local nor remote) is created from origin/<default> and pushed, with or without
--create. A Cargo.lock conflict takes INTEGRATION's lock, runs `cargo fetch` (then `cargo update -w` if
needed) and verifies with `cargo fetch --locked`; without cargo it stops and names the file.

DL241: a branch cut from a shared contract branch is not stacked on its sibling; stacked means B holds an older
head of A and the files both sides touched are listed (never an empty list). Every skipped branch prints
`skipped <branch>: <reason>`. A partial join ends with `joined N of M branches; skipped: <names>`; it exits 5 when a
branch was missing on the remote, and `--allow-partial` makes any skip (conflict, stacked, missing) exit 0.

Exit: 0 joined, 1 a result is not trusted or the gate/push failed, 2 usage or
configuration error (or no result), 3 stopped at a conflict or a stacked branch,
5 partial join: a branch was skipped because it is missing on the remote.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc
import gate_verify
import runner_health

# The steps of gate.json the light check runs, by name; a step's own "join": true/false wins.
QUICK_STEPS = ("typecheck", "lint")
EXIT_PARTIAL = 5  # DL241: a partial join with a branch missing on the remote (conflicts keep exit 3)


def write_join_result(root: Path, joined: list[str], stopped_at: str | None, conflicts: list[str],
                      reason: str | None = None, extra: dict | None = None) -> None:
    data: dict = {"joined": joined, "stopped_at": stopped_at, "conflicts": conflicts}
    if reason:
        data["reason"] = reason
    if extra:
        data.update(extra)
    dc.write_json(root / dc.JOIN_RESULT_PATH, data)


DOCS_SUMMARIES_PATH = ".delivery/docs-summaries.md"


def find_docs_script(name: str, home: str | None = None) -> Path | None:
    """A luismc-docs script: next to $LUISMC_DOCS_WORK, else the newest plugin cache copy, else the marketplace checkout."""
    env = os.environ.get("LUISMC_DOCS_WORK")
    if env:
        found_env = Path(env).parent / name
        return found_env if found_env.is_file() else None
    home = home or os.path.expanduser("~")
    found = glob.glob(os.path.join(home, ".claude", "plugins", "cache", "*", "luismc-docs", "*", "scripts", name))
    found.sort(key=lambda f: [int(x) if x.isdigit() else 0 for x in f.split(os.sep)[-3].split(".")])
    if found:
        return Path(found[-1])
    market = glob.glob(os.path.join(home, ".claude", "plugins", "marketplaces", "*", "claude", "plugins", "docs", "scripts", name))
    return Path(market[0]) if market else None


def find_docs_work(home: str | None = None) -> Path | None:
    """The luismc-docs `docs_work.py`."""
    return find_docs_script("docs_work.py", home)


DRAFT_DIR = "docs/design-system/next-version"


def rebuild_draft_gallery(root: Path, start: str) -> dict:
    """The join rebuilds the next-version review gallery when a joined branch changed that folder, and commits it.
    Skips cleanly (with a reason) when nothing changed there or the docs plugin is missing."""
    changed = dc.run_git(["diff", "--name-only", start, "HEAD", "--", DRAFT_DIR + "/"], cwd=root, check=False)
    if changed.returncode != 0 or not changed.stdout.strip():
        return {"rebuilt": False, "reason": "next-version unchanged"}
    script = find_docs_script("design_system.py")
    if script is None:
        print("join: luismc-docs is not installed; the next-version gallery was not rebuilt", flush=True)
        return {"rebuilt": False, "reason": "luismc-docs not present"}
    done = subprocess.run([sys.executable, str(script), "--root", str(root), "visuals", "next-version"],
                          capture_output=True, text=True, cwd=root)
    if done.returncode != 0:
        dc.eprint("join: design_system.py visuals failed (exit %d); going on: %s" % (done.returncode, (done.stderr or done.stdout).strip()))
        return {"rebuilt": False, "reason": "visuals failed"}
    dc.run_git(["add", "--", DRAFT_DIR], cwd=root, check=False)
    if dc.run_git(["diff", "--cached", "--quiet"], cwd=root, check=False).returncode != 0:
        dc.run_git(["commit", "-q", "-m", "Rebuild the next-version design-system gallery"], cwd=root, check=False, env=dc.git_env())
        print("join: rebuilt the next-version design-system gallery", flush=True)
        return {"rebuilt": True}
    return {"rebuilt": False, "reason": "gallery already current"}


def strip_temporary_docs(root: Path, base_ref: str | None = None) -> dict:
    """DOCSPEC R10.3: strip docs/work/ from the joined head and return {"stripped": bool, "summaries": [...]}.
    DL197: when `base_ref` has a docs/work/ folder, it is restored from there after the strip, so only paths the
    joined branches added or changed are removed (a changed file goes back to the base's content).
    Skips cleanly (stripped false, with a reason) when the docs plugin is absent or has nothing to strip."""
    script = find_docs_work()
    if script is None:
        print("join: luismc-docs is not installed; temporary agent docs not stripped", flush=True)
        return {"stripped": False, "reason": "luismc-docs not present", "summaries": []}
    base = [sys.executable, str(script), "--root", str(root)]
    got = subprocess.run(base + ["summaries"], capture_output=True, text=True, cwd=root)
    summaries = [l for l in got.stdout.splitlines() if l.strip()] if got.returncode == 0 else []
    had = (root / "docs" / "work").is_dir()
    if not had:
        return {"stripped": False, "reason": "no docs/work/", "summaries": summaries}
    done = subprocess.run(base + ["strip", "--apply"], capture_output=True, text=True, cwd=root)
    if done.returncode != 0:
        dc.eprint("join: docs_work.py strip failed (exit %d); going on: %s" % (done.returncode, (done.stderr or done.stdout).strip()))
        return {"stripped": False, "reason": "strip failed", "summaries": summaries}
    if base_ref and dc.run_git(["ls-tree", "-r", "--name-only", base_ref, "--", "docs/work"], cwd=root, check=False).stdout.strip():
        dc.run_git(["checkout", base_ref, "--", "docs/work"], cwd=root, check=False)
        dc.run_git(["add", "-A", "--", "docs/work"], cwd=root, check=False)
    if dc.run_git(["diff", "--cached", "--quiet"], cwd=root, check=False).returncode != 0:
        dc.run_git(["commit", "-q", "-m", "Strip temporary agent docs"], cwd=root, check=False, env=dc.git_env())
    print("join: stripped docs/work/ (%d report summaries kept for the PR body)" % len(summaries), flush=True)
    return {"stripped": True, "summaries": summaries}


def _names(root: Path, args: list[str]) -> set[str]:
    done = dc.run_git(["diff", "--name-only", *args], cwd=root, check=False)
    return {ln.strip() for ln in done.stdout.splitlines() if ln.strip()} if done.returncode == 0 else set()


def stacked_on_older(root: Path, remote: str, branch: str, others: list[str], trunk: str = "HEAD") -> tuple[str, list[str]] | None:
    """DL128, DL241: (A, files) when `branch` (B) contains an older head of another joined branch A but not A's
    current head, and both sides touch the same files: A's old work sits in B and A rewrote it later. A shared
    ancestor that is not a head of a joined branch (a contract branch the siblings are cut from) is not stacking.
    None when there is none."""
    b_ref = "refs/remotes/%s/%s" % (remote, branch)
    heads = {dc.rev("refs/remotes/%s/%s" % (remote, o), root) for o in others}
    for a in others:
        if a == branch:
            continue
        a_ref = "refs/remotes/%s/%s" % (remote, a)
        if dc.rev(a_ref, root) is None or dc.rev(b_ref, root) is None:
            continue
        a_in_b = dc.run_git(["merge-base", "--is-ancestor", a_ref, b_ref], cwd=root, check=False).returncode == 0
        if a_in_b:
            continue  # B carries A's whole head: nothing older
        base = dc.run_git(["merge-base", a_ref, b_ref], cwd=root, check=False)
        mb = base.stdout.strip() if base.returncode == 0 else ""
        if not mb:
            continue
        # The merge-base must be A's own older commit: not in the integration head, not a head of another
        # joined branch's sibling base, and not the tip of a remote branch outside this call (a contract branch).
        if dc.run_git(["merge-base", "--is-ancestor", mb, trunk], cwd=root, check=False).returncode == 0:
            continue
        tips = dc.run_git(["for-each-ref", "--format=%(objectname) %(refname)", "refs/remotes/%s/" % remote],
                          cwd=root, check=False).stdout.splitlines()
        shared = any(t.split(" ")[0] == mb and t.split(" ", 1)[1] not in
                     ("refs/remotes/%s/%s" % (remote, o) for o in others) for t in tips if " " in t)
        if shared:
            continue
        # B carries A's old work (trunk...mb); A rewrote those files after mb (mb..A).
        files = sorted(_names(root, [trunk + "..." + mb]) & _names(root, [mb, a_ref]))
        if files:
            return a, files
    return None


def is_docs_work(path: str) -> bool:
    return path.replace("\\", "/").startswith("docs/work/")


def resolve_docs_work(root: Path, paths: list[str]) -> bool:
    """DL145: a conflict under docs/work/ takes the branch's side (the strip removes them anyway)."""
    for path in paths:
        if dc.run_git(["checkout", "--theirs", "--", path], cwd=root, check=False).returncode != 0:
            if dc.run_git(["rm", "-q", "--", path], cwd=root, check=False).returncode != 0:
                return False
            continue
        dc.run_git(["add", "--", path], cwd=root, check=False)
    return True


MOCK_ERROR = "unhandled api call"


def mock_interaction_note(root: Path) -> str | None:
    """DL135: the note for a failed check whose logs hold an api-mock 'unhandled API call' error."""
    logs = root / dc.LOG_DIR / "join"
    if not logs.is_dir():
        return None
    for f in sorted(logs.rglob("*")):
        if f.is_file():
            try:
                if MOCK_ERROR in f.read_text(encoding="utf-8", errors="replace").lower():
                    return ("join-interaction failure: the e2e teardown reports an api-mock 'unhandled API call'. Each branch "
                            "passed alone; a call one branch added is not mocked by another branch's test. Add the mock "
                            "to the other branch's test (see %s)." % f.name)
            except OSError:
                continue
    return None


def pre_pr_docs(root: Path) -> dict:
    """DL140: the docs steps before the ready pull request. Each is skipped with a note when its script is absent."""
    out: dict = {"steps": {}, "t2_specs": []}

    def run(label: str, name: str, args: list[str]):
        script = find_docs_script(name)
        if script is None:
            print("join: luismc-docs %s not found; %s not run" % (name, label), flush=True)
            out["steps"][label] = "skipped: script absent"
            return None
        done = subprocess.run([sys.executable, str(script), "--root", str(root)] + args, capture_output=True, text=True, cwd=root)
        out["steps"][label] = "ok" if done.returncode == 0 else "failed (exit %d)" % done.returncode
        print("join: %s: %s" % (label, out["steps"][label]), flush=True)
        return done

    run("design-system visuals rebuild", "design_system.py", ["visuals", "--apply"]) if (root / "docs" / "design-system" / "next-version").is_dir() else None
    run("docs index build", "docs_index.py", ["build"])
    dc.run_git(["add", "--", "docs"], cwd=root, check=False)
    if dc.run_git(["diff", "--cached", "--quiet"], cwd=root, check=False).returncode != 0:
        dc.run_git(["commit", "-q", "-m", "Rebuild generated docs"], cwd=root, check=False, env=dc.git_env())
    done = run("docs check --strict", "docs_check.py", ["--strict"])
    if done is not None:
        specs = sorted({l.split()[2].rstrip(":") for l in done.stdout.splitlines()
                        if l.split()[:2] and len(l.split()) > 2 and l.split()[1] == "T2"})
        out["t2_specs"] = specs
        if specs:
            print("join: specs with T2 findings, verify before push:", flush=True)
            for sp in specs:
                print("    " + sp, flush=True)
    return out


def merge_in_progress(root: Path) -> bool:
    return dc.run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=root, check=False).returncode == 0


def abort_merge(root: Path) -> None:
    if merge_in_progress(root):
        dc.run_git(["merge", "--abort"], cwd=root, check=False)


def unmerged(root: Path) -> list[str]:
    out = dc.git(["diff", "--name-only", "--diff-filter=U", "-z"], cwd=root, check=False)
    return sorted(p for p in out.split("\0") if p)


GENERATED_DOCS = ("docs/index.html", "docs/llms.txt", "docs/features/index.md",
                  "docs/architecture/decisions.md", "docs/docs-map.json")
GENERATED_DOCS_DIRS = ("docs/_site/", "docs/reference/")


def is_generated_doc(path: str) -> bool:
    """DL249: a file `docs_index.py build` regenerates."""
    p = path.replace("\\", "/")
    return p in GENERATED_DOCS or p.startswith(GENERATED_DOCS_DIRS)


def resolve_generated_docs(root: Path, files: list[str]) -> str | None:
    """DL249: take INTEGRATION's version of generated docs, then rebuild them. None on success, else why not."""
    for path in files:
        if dc.run_git(["checkout", "--ours", "--", path], cwd=root, check=False).returncode != 0:
            dc.run_git(["rm", "-q", "--cached", "--", path], cwd=root, check=False)  # absent on integration
        else:
            dc.run_git(["add", "--", path], cwd=root, check=False)
    script = find_docs_script("docs_index.py")
    if script is None:
        return "docs_index.py not found, so the generated docs cannot be rebuilt"
    done = subprocess.run([sys.executable, str(script), "--root", str(root), "build"], capture_output=True, text=True, cwd=root)
    if done.returncode != 0:
        return "docs index build failed (exit %d)" % done.returncode
    dc.run_git(["add", "--", "docs"], cwd=root, check=False)
    return None


def conflict_files(files: list[str] | None) -> list[str]:
    """DL249: the list a conflict line prints; never empty."""
    return list(files) if files else ["(files unknown)"]


def is_cargo_lock(path: str) -> bool:
    return path.replace("\\", "/").rsplit("/", 1)[-1] == "Cargo.lock"


def resolve_cargo_lock(root: Path, path: str, run=None, which=None) -> str | None:
    """DL225: Cargo.lock already holds INTEGRATION's version. `cargo fetch` (not --locked) adds the
    branch's crates to it, then `cargo fetch --locked` proves the lock is complete. When fetch leaves
    the lock short, `cargo update -w` is tried once. Returns None on success, else why not."""
    run = run or dc.run_command
    which = which or shutil.which
    if which("cargo") is None:
        return "cargo is not installed, so %s cannot be updated for the branch's crates" % path
    print("==> cargo fetch (adds the branch's crates to %s)" % path, flush=True)
    if run("cargo fetch", root)[0] != 0:
        return "cargo fetch failed, so %s was not updated" % path
    if run("cargo fetch --locked", root)[0] != 0:
        print("==> cargo update -w (fetch left %s short)" % path, flush=True)
        if run("cargo update -w", root)[0] != 0 or run("cargo fetch --locked", root)[0] != 0:
            return "%s is still not complete after cargo fetch and cargo update -w" % path
    return None


def resolve_lockfiles(root: Path, cfg: dict, branch: str, lock: list[str], run=None, which=None) -> str | None:
    """Take INTEGRATION's lockfiles and re-run setup. Cargo.lock is updated by cargo instead
    (DL225). Returns None on success, else why it could not."""
    run = run or dc.run_command
    for path in lock:
        if dc.run_git(["checkout", "--ours", "--", path], cwd=root, check=False).returncode != 0:
            return "no integration version of %s to take" % path
        dc.run_git(["add", "--", path], cwd=root)
    cargo = [p for p in lock if is_cargo_lock(p)]
    for path in cargo:
        problem = resolve_cargo_lock(root, path, run, which)
        if problem is not None:
            return problem
    others = [p for p in lock if not is_cargo_lock(p)]
    if others or not cargo:
        for cmd in cfg["setup"]:
            if cargo and "cargo" in cmd:
                continue  # cargo was handled above, without --locked
            print("==> setup after lockfile resolution\n    $ %s" % cmd, flush=True)
            code, _ = run(cmd, root)
            if code != 0:
                return "setup failed (exit %d): %s" % (code, cmd)
    for path in lock:  # setup or cargo may have regenerated the lockfile
        dc.run_git(["add", "--", path], cwd=root)
    return None


def strip_remote(name: str, remotes: list[str]) -> str:
    """DL225: `origin/X` names the branch X. Strips one leading `<remote>/` of a configured remote."""
    for r in sorted(remotes, key=len, reverse=True):
        if name.startswith(r + "/") and len(name) > len(r) + 1:
            return name[len(r) + 1:]
    return name


def default_integration(branches: list[str]) -> str:
    """DL225: `<first task id>-integration`, the name the ready-PR guard accepts."""
    first = branches[0]
    m = re.match(r"^[A-Za-z]+[0-9]+[a-z]?(?=-|$)", first)
    tid = m.group(0) if m else first.split("-")[0].split("/")[-1]
    return "%s-integration" % tid


def trusted_same_tree(root: Path, remote: str, base_ref: str, joined: list[str]) -> str | None:
    """The first joined branch whose head has the joined head's tree and a gate result
    trusted for that head and for `base_ref` (the base the gate would use): running the
    gate again would test the same files against the same base. None when there is none."""
    def tree_of(ref: str) -> str | None:
        p = dc.run_git(["rev-parse", "--verify", "--quiet", ref + "^{tree}"], cwd=root, check=False)
        return p.stdout.strip() or None if p.returncode == 0 else None

    tree = tree_of("HEAD")
    for branch in joined:
        if tree is None or tree_of("refs/remotes/%s/%s" % (remote, branch)) != tree:
            continue
        if gate_verify.verify(branch, base_ref, remote, root=root)["trusted"]:
            return branch
    return None


def quick_steps(cfg: dict) -> list[dict]:
    """The gate.json steps the light check runs: typecheck and lint by default, any step with
    "join": true, never one with "join": false. A step keeps its own scope, so it sees the packages
    the merges touched ({changed_dirs}); no test step runs here."""
    return [dict(step) for step in cfg["steps"]
            if step.get("join") is True or (step.get("join") is None and step["name"] in QUICK_STEPS)]


def fast_guards_check(root: Path, base_ref: str) -> tuple[int, float]:
    """The pre_push steps on the joined head, through fast_guards.py. Returns (exit code, seconds)."""
    print("\njoin: fast guards of the joined head", flush=True)
    t0 = time.monotonic()
    code = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "fast_guards.py"), "--base-ref", base_ref],
        cwd=root).returncode
    return code, round(time.monotonic() - t0, 1)


def quick_check(root: Path, cfg: dict, base_ref: str) -> tuple[int, dict]:
    """Setup, typecheck/lint of the touched packages and the fast guards on the joined head.
    Returns (exit code, report)."""
    ctx = dc.build_context(root, cfg, base_ref)
    steps = quick_steps(cfg)
    minutes = cfg["timeout_minutes"]
    guards = cfg.get("join_guards", True) and any(s["pre_push"] for s in cfg["steps"])
    print("\njoin: light check of the joined head (setup, then %s%s)" % (
        ", ".join(s["name"] for s in steps) or "no step", ", fast guards" if guards else ""))
    print("      packages: %s" % (", ".join(ctx.changed_dirs) or "(none)")
          + ("  (widened: %s)" % ", ".join(ctx.widen_reasons[:3]) if ctx.widened else ""), flush=True)
    t0 = time.monotonic()
    entries, timed_out = dc.execute_steps(
        steps, ctx, setup_cmds=cfg["setup"], limit_seconds=minutes * 60, log_dir=dc.LOG_DIR + "/join")
    # No package changed is a pass here (nothing to check); overall_pass would call it "nothing ran".
    ok = not timed_out and not any(e["outcome"] == "fail" for e in entries)
    print("\n" + dc.summary_table(entries))
    dc.print_failures(entries, root)
    steps_report = [{"name": e["name"], "outcome": e["outcome"], "seconds": e["seconds"]} for e in entries]
    if ok and guards:
        gcode, gsec = fast_guards_check(root, base_ref)
        ok = gcode == 0
        steps_report.append({"name": "fast-guards", "outcome": "pass" if ok else "fail", "seconds": gsec})
    total = round(time.monotonic() - t0, 1)
    print("join: light check %s in %.1fs (%s)" % (
        "passed" if ok else "FAILED", total,
        ", ".join("%s %.1fs" % (e["name"], e["seconds"]) for e in steps_report if e["outcome"] != "skip") or "nothing ran"))
    report = {
        "base_ref": ctx.base_ref, "head": ctx.head, "widened": ctx.widened,
        "changed_dirs": ctx.changed_dirs, "affected_dirs": ctx.affected_dirs,
        "pass": ok, "timed_out": timed_out, "seconds": total, "steps": steps_report,
    }
    code = dc.EXIT_OK if ok else dc.EXIT_TIMEOUT if timed_out else dc.EXIT_FAIL
    return code, report


def finish_partial(root: Path, args, into: str, joined: list[str], conflicting: dict[str, list[str]],
                   stop_code: int | None, stop_branch: str | None, stop_reason: str | None,
                   skips: dict[str, str] | None = None) -> int:
    """DL111: some branch conflicted or was refused. The clean merges stay on the branch and are pushed with --push.

    The steps after the merges (docs stripping, gallery rebuild, light check, ready pull request text) do not run:
    they judge the whole join, and the join is not whole. They run in the call that joins the rest, which sees the
    full head. Exit is EXIT_CONFLICT for conflicts, or the refusal's own code when a refusal stopped the join."""
    skips = dict(skips or {})
    first = stop_branch or next(iter(conflicting or skips))
    for b in args.branches:  # DL241: a branch the loop never reached is skipped too
        if b not in joined and b not in skips:
            skips[b] = "not reached, the join stopped at %s" % stop_branch if stop_branch else "not joined"
    flat = [f for files in conflicting.values() for f in files]
    extra: dict = {"partial": True, "conflicting": conflicting, "skipped": skips, "pushed": False,
                   "skipped_steps": "docs stripping, gallery rebuild, light check and ready pull request text "
                                    "wait for the join of the remaining branches"}
    if stop_branch is not None:
        extra["refused"] = {"branch": stop_branch, "reason": stop_reason}
    for b, files in conflicting.items():
        dc.eprint("join: %s conflicts with %s in:" % (b, into))
        for f in conflict_files(files):
            dc.eprint("    " + f)
    if stop_branch is not None:
        dc.eprint("join: stopped at %s: %s" % (stop_branch, stop_reason))
    remote = args.remote
    head = dc.rev("HEAD", root)
    if joined:
        if args.push:
            pushed = dc.run_git(["push", "--quiet", "--no-verify", remote, into], cwd=root, check=False)
            if pushed.returncode != 0:
                dc.eprint("join: push of %s failed: %s; the clean merges stay committed on local %s"
                          % (into, pushed.stderr.strip(), into))
                write_join_result(root, joined, first, flat, stop_reason, extra=extra)
                return dc.EXIT_FAIL
            extra["pushed"] = True
            dc.ledger_record(root, "train_state", branch=into, state="pushed", by="join.py", create=True)
            dc.eprint("join: kept the clean merges (%s) and pushed %s; the other branches are left to do"
                      % (", ".join(joined), into))
        else:
            dc.eprint("join: kept the clean merges (%s), committed on local %s; not pushed (no --push)"
                      % (", ".join(joined), into))
        for b in joined:
            dc.ledger_record(root, "cargo", branch=into, task=b, by="join.py", create=True,
                             fields={"branch": b, "gate": "ci" if args.ci_gate else "pass", "joined_sha": head})
    else:
        dc.eprint("join: no branch merged cleanly; nothing kept")
    write_join_result(root, joined, first, flat, stop_reason, extra=extra)
    for b, why in skips.items():
        print("skipped %s: %s" % (b, why), flush=True)
    names = [b for b in args.branches if b not in joined]
    print("joined %d of %d branches; skipped: %s" % (len(joined), len(args.branches), ", ".join(names)), flush=True)
    if stop_code is not None:
        return stop_code
    if getattr(args, "allow_partial", False):
        return dc.EXIT_OK
    return dc.EXIT_CONFLICT if conflicting else EXIT_PARTIAL


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="join.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--into", default=None, metavar="INTEGRATION",
                    help="integration branch; default <first task id>-integration (DL225)")
    ap.add_argument("branches", nargs="+", metavar="BRANCH", help="branches to join, in order")
    ap.add_argument("--no-gate", action="store_true", help="skip the light check on the joined head")
    ap.add_argument("--ci-gate", action="store_true",
                    help="join branches whose gate is their branch CI run: no gate result required (DL-83)")
    ap.add_argument("--allow-partial", action="store_true",
                    help="exit 0 when branches were skipped (conflict, stacked, missing); the summary still prints")
    ap.add_argument("--push", action="store_true", help="push INTEGRATION (and its gate result) when done")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--create", action="store_true",
                    help="DL129: when INTEGRATION is not on the remote, push the default branch as INTEGRATION")
    args = ap.parse_args(argv)

    root = dc.repo_root()
    # STACKSPEC 13.8: a repository with no gate.json still joins; it says so and records that no gate ran.
    gated = (root / dc.GATE_JSON_PATH).is_file()
    cfg = dc.load_gate(root) if gated else {"setup": [], "lockfiles": [], "default_branch": "main", "steps": []}
    if not gated:
        print("join: the gate is not configured (no %s); joining without any gate" % dc.GATE_JSON_PATH, flush=True)
    dirty = dc.dirty_paths(root)
    if dirty:
        dc.eprint("error: working tree is not clean; commit or stash first:")
        for p in dirty[:10]:
            dc.eprint("    " + p)
        return dc.EXIT_USAGE
    if merge_in_progress(root):
        raise dc.DeliveryError("a merge is already in progress; finish or abort it first")

    remote = args.remote
    remotes = dc.run_git(["remote"], cwd=root, check=False).stdout.split()
    args.branches = [strip_remote(b, remotes) for b in args.branches]
    into = strip_remote(args.into, remotes) if args.into else default_integration(args.branches)
    if not args.into:
        print("join: no --into; using %s" % into, flush=True)
    started = int(time.time())  # branches born after this are left alone by the cleanup (DL99)
    # Worktrees of trains already merged go first. Best effort: it never stops a join.
    try:
        cleaned = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "cleanup.py"), "--local", "--remote", remote,
             "--keep-fresh-since", str(started)],
            cwd=root,
        ).returncode
        if cleaned != 0:
            dc.eprint("join: cleanup.py --local exited %d; going on" % cleaned)
    except OSError as exc:
        dc.eprint("join: cleanup.py --local could not run (%s); going on" % exc)
    dc.git(["fetch", "--quiet", remote], cwd=root)
    integ_ref = "%s/%s" % (remote, into)
    if dc.rev(integ_ref, root) is None:
        default_ref = "%s/%s" % (remote, cfg["default_branch"])
        create_cmd = "git push %s %s:refs/heads/%s" % (remote, default_ref, into)
        if not args.create and dc.rev("refs/heads/%s" % into, root) is not None:
            raise dc.DeliveryError("integration branch '%s' not found on remote '%s'; run again with --create, or create it: %s"
                                   % (into, remote, create_cmd))
        if dc.rev(default_ref, root) is None:
            raise dc.DeliveryError("cannot create '%s': %s not found" % (into, default_ref))
        if not args.create:
            print("join: %s is new (not local, not on %s); creating it (DL225)" % (into, remote), flush=True)
        made = dc.run_git(["push", "--quiet", "--no-verify", remote, "%s:refs/heads/%s" % (default_ref, into)], cwd=root, check=False)
        if made.returncode != 0:
            raise dc.DeliveryError("could not create '%s' on '%s': %s; create it yourself: %s"
                                   % (into, remote, made.stderr.strip(), create_cmd))
        print("join: created %s on %s from %s" % (into, remote, default_ref), flush=True)
        dc.git(["fetch", "--quiet", remote], cwd=root)
    # DL145: build on the local branch when it is ahead of the remote one; never drop local commits.
    local = dc.rev("refs/heads/%s" % into, root)
    remote_head = dc.rev(integ_ref, root)
    start_ref = integ_ref
    if local is not None and local != remote_head:
        if dc.run_git(["merge-base", "--is-ancestor", remote_head, local], cwd=root, check=False).returncode == 0:
            start_ref = "refs/heads/%s" % into
            print("join: local %s is ahead of %s; building on the local branch" % (into, integ_ref), flush=True)
        elif dc.run_git(["merge-base", "--is-ancestor", local, remote_head], cwd=root, check=False).returncode != 0:
            raise dc.DeliveryError(
                "local %s has commits that are not in %s and %s is not built on them; joining would lose them. "
                "Push or rebase local %s first." % (into, integ_ref, integ_ref, into))
    dc.git(["checkout", "--quiet", "-B", into, start_ref], cwd=root)
    print("join: %s at %s" % (into, dc.rev("HEAD", root)[:10]))

    ci_gate = args.ci_gate or bool(cfg.get("ci_gate"))
    join_start = dc.rev("HEAD", root)
    joined: list[str] = []
    conflicting: dict[str, list[str]] = {}  # DL111: branch -> its conflict files; skipped, the loop goes on
    stop_code: int | None = None  # DL111: set by a refusal or a failed merge; the loop ends, clean merges are kept
    stop_branch: str | None = None
    stop_reason: str | None = None
    skips: dict[str, str] = {}  # DL241: branch -> why it was skipped
    for branch in args.branches:
        if dc.rev("refs/remotes/%s/%s" % (remote, branch), root) is None:
            dc.eprint("join: %s is missing on %s" % (branch, remote))
            skips[branch] = "missing on %s" % remote
            continue
        verdict = gate_verify.verify(branch, integ_ref, remote, allow_older_base=True, root=root) if gated else None
        if verdict is not None and not verdict["trusted"] and ci_gate:
            print("join: %s has no gate result; joined at code push, its branch CI run is its gate (ci_gate)" % branch,
                  flush=True)
        elif verdict is not None and not verdict["trusted"]:
            dc.eprint("join: %s has no trusted passing gate result:" % branch)
            for reason in verdict["reasons"]:
                dc.eprint("  - " + reason)
            stop_code, stop_branch, stop_reason = verdict["exit"], branch, "; ".join(verdict["reasons"])
            skips[branch] = "not ready, no trusted passing gate result: " + stop_reason
            break

        older = stacked_on_older(root, remote, branch, args.branches, join_start)
        if older is not None:
            older, st_files = older
            reason = "%s is stacked on an older %s; prefer %s's side for files %s rewrote" % (branch, older, branch, branch)
            dc.eprint("join: " + reason)
            dc.eprint("join: files in both: " + ", ".join(st_files))
            dc.eprint("join: merge %s alone (it carries %s's older work) or rebase %s on the current %s" % (branch, older, branch, older))
            conflicting[branch] = st_files
            skips[branch] = "stacked on an older %s, files: %s" % (older, ", ".join(st_files))
            stop_reason = reason
            continue

        print("join: merging %s" % branch, flush=True)
        merge = dc.run_git(
            ["merge", "--no-ff", "-m", "Join %s" % branch, "%s/%s" % (remote, branch)],
            cwd=root,
            check=False,
            env=dc.git_env(),
        )
        if merge.returncode == 0:
            print(merge.stdout.strip())
            joined.append(branch)
            continue

        conflicts = unmerged(root)
        if not conflicts:
            abort_merge(root)
            dc.eprint("join: git merge failed for %s: %s" % (branch, (merge.stderr or merge.stdout).strip()))
            stop_code, stop_branch, stop_reason = dc.EXIT_USAGE, branch, "merge failed"
            skips[branch] = "merge failed"
            break

        work_files = [c for c in conflicts if is_docs_work(c)]
        if work_files:
            if resolve_docs_work(root, work_files):
                print("join: %s: took the branch's side of %s under docs/work/ (the strip removes them)" % (branch, ", ".join(work_files)), flush=True)
                conflicts = unmerged(root)
                if not conflicts:
                    commit = dc.run_git(["commit", "--no-edit"], cwd=root, check=False, env=dc.git_env())
                    if commit.returncode == 0:
                        joined.append(branch)
                        continue
                    abort_merge(root)
                    conflicting[branch] = work_files
                    continue
        lock = [c for c in conflicts if dc.is_lockfile(c, cfg)]
        if len(lock) == len(conflicts):
            print("join: %s conflicts only in %s; taking %s's version and re-running setup" % (branch, ", ".join(lock), into))
            problem = resolve_lockfiles(root, cfg, branch, lock)
            if problem is not None:
                abort_merge(root)
                dc.eprint("join: could not resolve the lockfile conflict: %s" % problem)
                conflicting[branch] = conflicts
                continue
            commit = dc.run_git(["commit", "--no-edit"], cwd=root, check=False, env=dc.git_env())
            if commit.returncode != 0:
                abort_merge(root)
                dc.eprint("join: could not commit the resolved merge: %s" % (commit.stderr or commit.stdout).strip())
                conflicting[branch] = conflicts
                continue
            joined.append(branch)
            continue

        gen = [c for c in conflicts if is_generated_doc(c)]
        if gen and len(gen) == len(conflicts):
            problem = resolve_generated_docs(root, gen)
            commit = None
            if problem is None:
                commit = dc.run_git(["commit", "--no-edit"], cwd=root, check=False, env=dc.git_env())
                if commit.returncode != 0:
                    problem = "could not commit the resolved merge: %s" % (commit.stderr or commit.stdout).strip()
            if problem is None:
                print("join: %s conflicts only in generated docs (%s); took %s's version and rebuilt them with docs index build"
                      % (branch, ", ".join(gen), into), flush=True)
                joined.append(branch)
                continue
            dc.eprint("join: could not resolve the generated docs conflict: %s" % problem)

        abort_merge(root)
        conflicting[branch] = conflicts

    for b, files in conflicting.items():
        skips.setdefault(b, "conflict with %s in: %s" % (into, ", ".join(conflict_files(files))))
    if conflicting or skips or stop_code is not None:
        return finish_partial(root, args, into, joined, conflicting, stop_code, stop_branch, stop_reason, skips)

    write_join_result(root, joined, None, [])

    docs = strip_temporary_docs(root, "%s/%s" % (remote, cfg["default_branch"]))
    gallery = rebuild_draft_gallery(root, join_start) if join_start else {"rebuilt": False, "reason": "no start"}
    docs_extra: dict = {"docs": {k: v for k, v in docs.items() if k != "summaries"}, "docs_summaries": docs["summaries"],
                        "gallery": gallery}
    if docs["summaries"]:
        out = root / DOCS_SUMMARIES_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(docs["summaries"]) + "\n", encoding="utf-8", newline="\n")

    base_ref = "%s/%s" % (remote, cfg["default_branch"])
    same = None if args.no_gate or not gated else trusted_same_tree(root, remote, base_ref, joined)
    extra: dict = dict(docs_extra)
    if not gated:
        extra["gate"] = "not configured"
        extra["quick_check"] = {"skipped": "gate not configured"}
        print("join: no gate ran: the gate is not configured", flush=True)
    elif same is not None:
        print("\njoin: gate on the joined head skipped: its tree equals that of %s, whose gate result "
              "is trusted for that head and for %s" % (same, base_ref), flush=True)
        extra["quick_check"] = {"skipped": "tree equals that of %s" % same}
    elif not args.no_gate:
        code, qc = quick_check(root, cfg, base_ref)
        extra["quick_check"] = qc
        write_join_result(root, joined, None, [], extra=extra)
        if code != 0:
            note = mock_interaction_note(root)
            if note:
                dc.eprint("join: " + note)
                extra["quick_check"]["join_interaction"] = note
                write_join_result(root, joined, None, [], extra=extra)
            dc.eprint("join: the light check on the joined head did not pass (exit %d); nothing pushed" % code)
            return code if code in (dc.EXIT_FAIL, dc.EXIT_USAGE, dc.EXIT_TIMEOUT) else dc.EXIT_FAIL

    extra["pre_pr_docs"] = pre_pr_docs(root)
    # Runner health (DL7): warnings only, never a reason to stop.
    try:
        health = runner_health.check(root)
        print("")
        runner_health.report(health, "join: runner health")
        extra["runner_health"] = {k: health[k] for k in ("status", "warnings", "reason")}
    except Exception as exc:  # a broken check must never stop a join
        print("join: runner health: check skipped: %s" % exc)
    write_join_result(root, joined, None, [], extra=extra)

    if args.push:
        pushed = dc.run_git(["push", "--quiet", "--no-verify", remote, into], cwd=root, check=False)
        if pushed.returncode != 0:
            dc.eprint("join: push of %s failed: %s" % (into, pushed.stderr.strip()))
            return dc.EXIT_FAIL
        print("join: pushed %s" % into)
        dc.ledger_record(root, "train_state", branch=into, state="pushed", by="join.py", create=True)

    head = dc.rev("HEAD", root)
    for b in joined:
        dc.ledger_record(root, "cargo", branch=into, task=b, by="join.py", create=True,
                         fields={"branch": b, "gate": "pass" if gated else "none", "joined_sha": head})
    dc.ledger_record(root, "train_state", branch=into, state="joined", by="join.py", create=True)
    print("join: joined %s" % ", ".join(joined))
    return dc.EXIT_OK


if __name__ == "__main__":
    dc.main_guard(main)
