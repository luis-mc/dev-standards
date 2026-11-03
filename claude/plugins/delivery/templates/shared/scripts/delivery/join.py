#!/usr/bin/env python3
"""Join gated branches into the integration branch (STACKSPEC 13.6).

    join.py --into INTEGRATION BRANCH [BRANCH ...] [--no-gate] [--ci-gate] [--push] [--remote origin]

Runs `cleanup.py --local` (best effort), fetches, checks out INTEGRATION at its
remote head, and for each BRANCH in order:
requires a trusted, passing gate result (a base older than INTEGRATION's head is
fine), then merges it with `git merge --no-ff -m "Join BRANCH"`. A conflict that
touches only a lockfile is resolved by taking INTEGRATION's version and re-running
gate.json's `setup`; any other conflict aborts that merge, writes
.delivery/join-result.json and exits 3. After the last merge a light check runs on the
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

Exit: 0 joined, 1 a result is not trusted or the gate/push failed, 2 usage or
configuration error (or no result), 3 stopped at a conflict.
"""
from __future__ import annotations

import argparse
import glob
import os
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


def write_join_result(root: Path, joined: list[str], stopped_at: str | None, conflicts: list[str],
                      reason: str | None = None, extra: dict | None = None) -> None:
    data: dict = {"joined": joined, "stopped_at": stopped_at, "conflicts": conflicts}
    if reason:
        data["reason"] = reason
    if extra:
        data.update(extra)
    dc.write_json(root / dc.JOIN_RESULT_PATH, data)


DOCS_SUMMARIES_PATH = ".delivery/docs-summaries.md"


def find_docs_work(home: str | None = None) -> Path | None:
    """The luismc-docs `docs_work.py`: $LUISMC_DOCS_WORK, else the newest plugin cache copy, else the marketplace checkout."""
    env = os.environ.get("LUISMC_DOCS_WORK")
    if env:
        return Path(env) if Path(env).is_file() else None
    home = home or os.path.expanduser("~")
    found = glob.glob(os.path.join(home, ".claude", "plugins", "cache", "*", "luismc-docs", "*", "scripts", "docs_work.py"))
    found.sort(key=lambda f: [int(x) if x.isdigit() else 0 for x in f.split(os.sep)[-3].split(".")])
    if found:
        return Path(found[-1])
    market = glob.glob(os.path.join(home, ".claude", "plugins", "marketplaces", "*", "claude", "plugins", "docs", "scripts", "docs_work.py"))
    return Path(market[0]) if market else None


def strip_temporary_docs(root: Path) -> dict:
    """DOCSPEC R10.3: strip docs/work/ from the joined head and return {"stripped": bool, "summaries": [...]}.
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
    if dc.run_git(["diff", "--cached", "--quiet"], cwd=root, check=False).returncode != 0:
        dc.run_git(["commit", "-q", "-m", "Strip temporary agent docs"], cwd=root, check=False, env=dc.git_env())
    print("join: stripped docs/work/ (%d report summaries kept for the PR body)" % len(summaries), flush=True)
    return {"stripped": True, "summaries": summaries}


def merge_in_progress(root: Path) -> bool:
    return dc.run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=root, check=False).returncode == 0


def abort_merge(root: Path) -> None:
    if merge_in_progress(root):
        dc.run_git(["merge", "--abort"], cwd=root, check=False)


def unmerged(root: Path) -> list[str]:
    out = dc.git(["diff", "--name-only", "--diff-filter=U", "-z"], cwd=root, check=False)
    return sorted(p for p in out.split("\0") if p)


def resolve_lockfiles(root: Path, cfg: dict, branch: str, lock: list[str]) -> str | None:
    """Take INTEGRATION's lockfiles and re-run setup. Returns None on success,
    else why it could not."""
    for path in lock:
        if dc.run_git(["checkout", "--ours", "--", path], cwd=root, check=False).returncode != 0:
            return "no integration version of %s to take" % path
        dc.run_git(["add", "--", path], cwd=root)
    for cmd in cfg["setup"]:
        print("==> setup after lockfile resolution\n    $ %s" % cmd, flush=True)
        code, _ = dc.run_command(cmd, root)
        if code != 0:
            return "setup failed (exit %d): %s" % (code, cmd)
    for path in lock:  # setup may have regenerated the lockfile
        dc.run_git(["add", "--", path], cwd=root)
    return None


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="join.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--into", required=True, metavar="INTEGRATION", help="integration branch")
    ap.add_argument("branches", nargs="+", metavar="BRANCH", help="branches to join, in order")
    ap.add_argument("--no-gate", action="store_true", help="skip the light check on the joined head")
    ap.add_argument("--ci-gate", action="store_true",
                    help="join branches whose gate is their branch CI run: no gate result required (DL-83)")
    ap.add_argument("--push", action="store_true", help="push INTEGRATION (and its gate result) when done")
    ap.add_argument("--remote", default="origin")
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

    remote, into = args.remote, args.into
    # Worktrees of trains already merged go first. Best effort: it never stops a join.
    try:
        cleaned = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "cleanup.py"), "--local", "--remote", remote],
            cwd=root,
        ).returncode
        if cleaned != 0:
            dc.eprint("join: cleanup.py --local exited %d; going on" % cleaned)
    except OSError as exc:
        dc.eprint("join: cleanup.py --local could not run (%s); going on" % exc)
    dc.git(["fetch", "--quiet", remote], cwd=root)
    integ_ref = "%s/%s" % (remote, into)
    if dc.rev(integ_ref, root) is None:
        raise dc.DeliveryError("integration branch '%s' not found on remote '%s'" % (into, remote))
    dc.git(["checkout", "--quiet", "-B", into, integ_ref], cwd=root)
    print("join: %s at %s" % (into, dc.rev("HEAD", root)[:10]))

    ci_gate = args.ci_gate or bool(cfg.get("ci_gate"))
    joined: list[str] = []
    for branch in args.branches:
        verdict = gate_verify.verify(branch, integ_ref, remote, allow_older_base=True, root=root) if gated else None
        if verdict is not None and not verdict["trusted"] and ci_gate:
            print("join: %s has no gate result; joined at code push, its branch CI run is its gate (ci_gate)" % branch,
                  flush=True)
        elif verdict is not None and not verdict["trusted"]:
            dc.eprint("join: %s has no trusted passing gate result:" % branch)
            for reason in verdict["reasons"]:
                dc.eprint("  - " + reason)
            write_join_result(root, joined, branch, [], "; ".join(verdict["reasons"]))
            return verdict["exit"]

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
            write_join_result(root, joined, branch, [], "merge failed")
            return dc.EXIT_USAGE

        lock = [c for c in conflicts if dc.is_lockfile(c, cfg)]
        if len(lock) == len(conflicts):
            print("join: %s conflicts only in %s; taking %s's version and re-running setup" % (branch, ", ".join(lock), into))
            problem = resolve_lockfiles(root, cfg, branch, lock)
            if problem is not None:
                abort_merge(root)
                dc.eprint("join: could not resolve the lockfile conflict: %s" % problem)
                write_join_result(root, joined, branch, conflicts, problem)
                return dc.EXIT_CONFLICT
            commit = dc.run_git(["commit", "--no-edit"], cwd=root, check=False, env=dc.git_env())
            if commit.returncode != 0:
                abort_merge(root)
                dc.eprint("join: could not commit the resolved merge: %s" % (commit.stderr or commit.stdout).strip())
                write_join_result(root, joined, branch, conflicts, "commit failed")
                return dc.EXIT_CONFLICT
            joined.append(branch)
            continue

        abort_merge(root)
        dc.eprint("join: %s conflicts with %s in:" % (branch, into))
        for c in conflicts:
            dc.eprint("    " + c)
        write_join_result(root, joined, branch, conflicts)
        return dc.EXIT_CONFLICT

    write_join_result(root, joined, None, [])

    docs = strip_temporary_docs(root)
    docs_extra: dict = {"docs": {k: v for k, v in docs.items() if k != "summaries"}, "docs_summaries": docs["summaries"]}
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
            dc.eprint("join: the light check on the joined head did not pass (exit %d); nothing pushed" % code)
            return code if code in (dc.EXIT_FAIL, dc.EXIT_USAGE, dc.EXIT_TIMEOUT) else dc.EXIT_FAIL

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
        dc.ledger_record(root, "train_state", branch=into, state="pushed", by="join.py")

    head = dc.rev("HEAD", root)
    for b in joined:
        dc.ledger_record(root, "cargo", branch=into, task=b, by="join.py",
                         fields={"branch": b, "gate": "pass" if gated else "none", "joined_sha": head})
    dc.ledger_record(root, "train_state", branch=into, state="joined", by="join.py")
    print("join: joined %s" % ", ".join(joined))
    return dc.EXIT_OK


if __name__ == "__main__":
    dc.main_guard(main)
