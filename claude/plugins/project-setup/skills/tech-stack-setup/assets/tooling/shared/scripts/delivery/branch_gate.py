#!/usr/bin/env python3
"""Branch gate (STACKSPEC 13.5): the one command run on a branch before it joins.

    branch_gate.py [--base-ref REF] [--full] [--only a,b] [--skip a,b] [--no-publish]
                   [--keep-going] [--no-setup] [--timeout-minutes N]

Installs from the lockfile (gate.json "setup"), then runs the steps of
scripts/delivery/gate.json against the merge base with the branch it will join,
stopping at the first failure. Writes .delivery/gate-result.json (step logs in
.delivery/logs/) and publishes it as a parentless commit at
refs/gate-results/<branch> on the remote. See CONTRACT.md.

Exit: 0 pass, 1 a step failed (or nothing ran), 2 usage/configuration error,
4 timed out.
"""
from __future__ import annotations

import argparse
import sys

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc


def publish_result(root, remote: str, branch: str, result_file) -> str:
    """Push the result file as a parentless commit at refs/gate-results/<branch>.
    Returns the commit sha. One ref per branch, force-pushed, so parallel agents
    never contend and the result never touches the branch itself."""
    text = result_file.read_text(encoding="utf-8")
    blob = dc.git(["hash-object", "-w", "--stdin"], cwd=root, input_text=text)
    tree = dc.git(
        ["mktree"],
        cwd=root,
        input_text="100644 blob %s\t%s\n" % (blob, dc.RESULT_FILE_IN_REF),
    )
    commit = dc.git(
        ["commit-tree", tree, "-m", "gate result: %s" % branch],
        cwd=root,
        env=dc.git_env(),
    )
    # --no-verify: pushing a result ref must not run the pre-push guards.
    dc.git(
        ["push", "--quiet", "--no-verify", "--force", remote, "%s:%s%s" % (commit, dc.RESULT_REF_PREFIX, branch)],
        cwd=root,
    )
    return commit


def parse_names(value: str | None, valid: list[str], flag: str) -> set[str] | None:
    if value is None:
        return None
    names = {n.strip() for n in value.split(",") if n.strip()}
    unknown = sorted(names - set(valid))
    if unknown:
        raise dc.DeliveryError(
            "%s: unknown step(s) %s (steps: %s)" % (flag, ", ".join(unknown), ", ".join(valid))
        )
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="branch_gate.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-ref", help="branch this one will join (default origin/<default_branch>)")
    ap.add_argument("--full", action="store_true", help="widen to every package (run_full commands)")
    ap.add_argument("--only", help="comma-separated step names to run; the rest are skipped")
    ap.add_argument("--skip", help="comma-separated step names to skip")
    ap.add_argument("--no-publish", action="store_true", help="write the result locally only")
    ap.add_argument("--keep-going", action="store_true", help="run every selected step even after one fails")
    ap.add_argument("--fail-fast", action="store_true", help="accepted and ignored: stopping at the first failure is the default")
    ap.add_argument("--no-setup", action="store_true", help="skip the install from the lockfile; the run is partial")
    ap.add_argument("--timeout-minutes", type=float, metavar="N",
                    help="wall-clock limit for the whole run (default: gate.json timeout_minutes, 30)")
    args = ap.parse_args(argv)
    if args.timeout_minutes is not None and not args.timeout_minutes > 0:
        ap.error("--timeout-minutes must be greater than 0")

    root = dc.repo_root()
    cfg = dc.load_gate(root)
    steps = cfg["steps"]
    names = [s["name"] for s in steps]
    only = parse_names(args.only, names, "--only")
    skip = parse_names(args.skip, names, "--skip") or set()
    partial = only is not None or bool(skip) or args.no_setup
    selected = (only if only is not None else set(names)) - skip

    dirty = dc.dirty_paths(root)
    if dirty:
        dc.eprint("error: working tree is not clean; commit or stash first (the gate tests committed work):")
        for p in dirty[:10]:
            dc.eprint("    " + p)
        return dc.EXIT_USAGE

    branch = dc.current_branch(root)
    publish = not args.no_publish and not partial
    if publish and not branch:
        raise dc.DeliveryError("HEAD is detached; check out the branch, or pass --no-publish")

    ctx = dc.build_context(root, cfg, args.base_ref, full=args.full)
    remote = dc.remote_of(ctx.base_ref, cwd=root)

    print("branch  : %s" % (branch or "(detached)"))
    print("head    : %s" % ctx.head)
    print("base    : %s  (merge-base with %s)" % (ctx.base, ctx.base_ref))
    print("changed : %s" % (", ".join(ctx.changed_dirs) or "(no package)"))
    if ctx.widened:
        shown = ", ".join(ctx.widen_reasons[:5]) + (" ..." if len(ctx.widen_reasons) > 5 else "")
        print("widened : yes (%s)" % shown)
    minutes = args.timeout_minutes if args.timeout_minutes is not None else cfg["timeout_minutes"]
    print("limit   : %g min" % minutes)

    started = dc.utc_now()
    entries, timed_out = dc.execute_steps(
        steps,
        ctx,
        selected=selected,
        keep_going=args.keep_going,
        setup_cmds=cfg["setup"],
        no_setup=args.no_setup,
        limit_seconds=minutes * 60,
    )
    finished = dc.utc_now()

    ok = dc.overall_pass(entries, timed_out)
    result = {
        "schema": dc.SCHEMA,
        "kind": "branch-gate",
        "branch": branch,
        "head": ctx.head,
        "base": ctx.base,
        "base_ref": ctx.base_ref,
        "widened": ctx.widened,
        "changed_dirs": ctx.changed_dirs,
        "steps": entries,
        "pass": ok,
        "timed_out": timed_out,
        "partial": partial,
        "started_at": started,
        "finished_at": finished,
        "tool": "branch_gate.py %d" % dc.TOOL_VERSION,
    }
    result_file = root / dc.GATE_RESULT_PATH
    dc.write_json(result_file, result)

    print("\n" + dc.summary_table(entries))
    dc.print_failures(entries, root)
    if any(e["name"] == dc.SETUP_STEP and e["outcome"] == "fail" and not timed_out for e in entries):
        print("\nsetup   : failed, so no other step ran. A stale lockfile is the usual cause:")
        print("          regenerate it with the package manager's normal install, commit it, run the gate again.")
    if timed_out:
        dc.eprint("error: the gate timed out after %g min; the running step was killed" % minutes)
    print("\nresult  : %s -> %s" % ("PASS" if ok else "FAIL", dc.GATE_RESULT_PATH))

    exit_code = dc.EXIT_OK if ok else dc.EXIT_TIMEOUT if timed_out else dc.EXIT_FAIL
    if partial:
        print("note    : --only/--skip/--no-setup used; this result is partial and is not published or trusted")
    elif not args.no_publish:
        try:
            publish_result(root, remote, branch, result_file)
            print("publish : %s%s on %s" % (dc.RESULT_REF_PREFIX, branch, remote))
        except dc.DeliveryError as exc:
            dc.eprint("error: could not publish the result: %s" % exc)
            dc.eprint("        pass --no-publish to run without a remote")
            if ok:
                exit_code = dc.EXIT_USAGE
    if not any(e["outcome"] != "skip" for e in entries):
        dc.eprint("error: no step ran, so the gate cannot decide (exit 1)")
    return exit_code


if __name__ == "__main__":
    dc.main_guard(main)
