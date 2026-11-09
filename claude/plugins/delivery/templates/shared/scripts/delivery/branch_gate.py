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
import os
import platform
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc


# Gate output is UTF-8 on every OS (DL134).
CHILD_ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "FORCE_COLOR": "0", "NO_COLOR": "1"}
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Where e2e runs write screenshots; restored after the run (DL131).
GATE_OUTPUT_DIRS = ("docs/work",)
WINDOWS_ONLY_RE = re.compile(r"-windows|UseWPF|UseWindowsForms|net4\d\d?\b|<TargetFrameworkVersion>", re.I)


def prepare_environment() -> None:
    """Children inherit this: UTF-8 I/O and no colour codes in their output."""
    for key, value in CHILD_ENV.items():
        os.environ[key] = value
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def decode_log_bytes(data: bytes) -> str:
    """Child output as text: UTF-8 when it is, else the Windows code page; never raises.
    ANSI colour sequences are removed."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    return ANSI_RE.sub("", text)


def normalize_logs(root, entries) -> None:
    """Rewrite each step log as clean UTF-8, so cat and Python can read it anywhere."""
    for e in entries:
        rel = e.get("log")
        if not rel:
            continue
        path = root / rel
        try:
            text = decode_log_bytes(path.read_bytes())
            path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
        except OSError:
            continue


def restore_gate_outputs(root, dirs=GATE_OUTPUT_DIRS) -> list[str]:
    """The tree was clean when the gate began, so whatever is modified or untracked
    under these directories now was written by the gate's own steps (e2e screenshots).
    Restore tracked files and remove new ones there only. Returns the paths touched."""
    touched = []
    for d in dirs:
        if not (root / d).exists():
            continue
        out = dc.run_git(["status", "--porcelain", "--untracked-files=all", "--", d], cwd=root, check=False).stdout
        touched += [line[3:] for line in out.splitlines() if len(line) > 3]
        dc.run_git(["restore", "--staged", "--worktree", "--", d], cwd=root, check=False)
        dc.run_git(["clean", "-fdq", "--", d], cwd=root, check=False)
    return touched


def os_name() -> str:
    return platform.system() or sys.platform


def csharp_projects(root, files) -> list[str]:
    """The .csproj files that the changed .cs and .csproj files belong to."""
    projects: set[str] = set()
    for f in files:
        low = f.lower()
        if low.endswith(".csproj"):
            projects.add(f)
        elif low.endswith(".cs"):
            d = (root / f).parent
            while True:
                found = sorted(d.glob("*.csproj")) if d.is_dir() else []
                if found:
                    projects.add(found[0].relative_to(root).as_posix())
                    break
                if d == root or root not in d.parents:
                    break
                d = d.parent
    return sorted(projects)


def csharp_check(root, files, run=subprocess.run, which=shutil.which, system=None):
    """Compile changed C# where this OS can (DL141). Returns (warnings, failures).
    A Linux gate cannot build Windows-only projects: it says so, and release CI compiles."""
    changed = [f for f in files if f.lower().endswith((".cs", ".csproj"))]
    if not changed:
        return [], []
    system = system or os_name()
    warn = "C# changed, not compiled on %s (release CI compiles it)" % system
    if not which("dotnet"):
        return [warn + ": dotnet is not installed"], []
    projects = csharp_projects(root, changed)
    if not projects:
        return [warn + ": no .csproj found for the changed files"], []
    warnings, failures = [], []
    for proj in projects:
        try:
            text = (root / proj).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            text = ""
        if system != "Windows" and WINDOWS_ONLY_RE.search(text):
            warnings.append(warn + ": %s is Windows-only" % proj)
            continue
        try:
            p = run(["dotnet", "build", proj, "--nologo", "-v", "q"], cwd=root, capture_output=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired) as exc:
            warnings.append(warn + ": %s: %s" % (proj, exc))
            continue
        if p.returncode != 0:
            tail = decode_log_bytes(p.stdout or b"").strip().splitlines()[-5:]
            failures.append("%s: dotnet build failed: %s" % (proj, " | ".join(tail)))
    return warnings, failures


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


MEMORY_SENTENCE = ("setup was killed for memory (exit code 137, or 'Killed' in the log): "
                   "use a larger pool cap or fewer parallel jobs, not a new lockfile.")
LOCKFILE_SENTENCE = ("a stale lockfile: regenerate it with the package manager's normal install, "
                     "commit it, run the gate again. Never install unfrozen.")


def setup_failure_lines(exit_code):
    """Text for a failed setup step. Exit code 137 means killed for memory, so that cause goes first."""
    first, second = (MEMORY_SENTENCE, LOCKFILE_SENTENCE) if exit_code == 137 else (LOCKFILE_SENTENCE, MEMORY_SENTENCE)
    return [
        "\nsetup   : failed, so no other step ran. There are two common causes:",
        "          1. " + first,
        "          2. Or " + second[0].lower() + second[1:],
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="branch_gate.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-ref", help="branch this one will join (default origin/<default_branch>)")
    ap.add_argument("--full", action="store_true", help="widen to every package (run_full commands)")
    ap.add_argument("--only", help="comma-separated step names to run; the rest are skipped")
    ap.add_argument("--skip", help="comma-separated step names to skip")
    ap.add_argument("--no-publish", action="store_true", help="write the result locally only")
    ap.add_argument("--keep-going", action="store_true", help="run every selected step even after one fails")
    ap.add_argument("--fail-fast", action="store_true", help="accepted and ignored: stopping at the first failure is the default")
    ap.add_argument("--e2e-only", action="store_true",
                    help="run only the e2e step (the specs of the screens this branch changes) and publish the "
                         "record; for an agent on the CI-gate path (DL-86, DL-87)")
    ap.add_argument("--no-setup", action="store_true", help="skip the install from the lockfile; the run is partial")
    ap.add_argument("--timeout-minutes", type=float, metavar="N",
                    help="wall-clock limit for the whole run (default: gate.json timeout_minutes, 30)")
    args = ap.parse_args(argv)
    if args.timeout_minutes is not None and not args.timeout_minutes > 0:
        ap.error("--timeout-minutes must be greater than 0")

    prepare_environment()
    root = dc.repo_root()
    cfg = dc.load_gate(root)
    steps = cfg["steps"]
    names = [s["name"] for s in steps]
    if args.e2e_only:
        e2e = dc.e2e_step(cfg)
        if e2e is None:
            raise dc.DeliveryError("--e2e-only: gate.json has no ui-changed (e2e) step")
        if args.only:
            raise dc.DeliveryError("--e2e-only cannot be combined with --only")
        args.only = e2e["name"]
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
    publish = not args.no_publish and (not partial or args.e2e_only)
    if publish and not branch:
        raise dc.DeliveryError("HEAD is detached; check out the branch, or pass --no-publish")

    ctx = dc.build_context(root, cfg, args.base_ref, full=args.full)
    remote = dc.remote_of(ctx.base_ref, cwd=root)

    print("branch  : %s" % (branch or "(detached)"))
    print("head    : %s" % ctx.head)
    print("base    : %s  (merge-base with %s)" % (ctx.base, ctx.base_ref))
    print("fetched : %s" % ("yes" if ctx.base_fetched else "no (local ref used)"))
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
        required_steps=cfg["required_steps"],
    )
    finished = dc.utc_now()
    normalize_logs(root, entries)
    restored = restore_gate_outputs(root)
    if restored:
        print("restored: %d file(s) the gate wrote under %s" % (len(restored), ", ".join(GATE_OUTPUT_DIRS)))

    cs_warnings, cs_failures = ([], [])
    if only is None and not skip:
        cs_warnings, cs_failures = csharp_check(root, ctx.files)
    for msg in cs_failures:
        entries.append({"name": "csharp-build", "outcome": "fail", "seconds": 0.0, "command": "dotnet build",
                        "reason": msg, "exit_code": 1})

    ok = dc.overall_pass(entries, timed_out)
    result = {
        "schema": dc.SCHEMA,
        "kind": "branch-gate",
        "branch": branch,
        "head": ctx.head,
        "base": ctx.base,
        "base_ref": ctx.base_ref,
        "base_fetched": ctx.base_fetched,
        "widened": ctx.widened,
        "changed_dirs": ctx.changed_dirs,
        "steps": entries,
        "required_steps": cfg["required_steps"],
        "pass": ok,
        "timed_out": timed_out,
        "partial": partial,
        "e2e_only": bool(args.e2e_only),
        "ui_changed": bool(dc.ui_files(ctx)),
        "e2e": dc.e2e_record(entries, ctx),
        "started_at": started,
        "finished_at": finished,
        "tool": "branch_gate.py %d" % dc.TOOL_VERSION,
    }
    if cs_warnings:
        result["warnings"] = cs_warnings  # only present when a C# change was not compiled (DL141)
    result_file = root / dc.GATE_RESULT_PATH
    dc.write_json(result_file, result)

    print("\n" + dc.summary_table(entries))
    for w in cs_warnings:
        print("warning : %s" % w)
    dc.print_failures(entries, root)
    if any(e["name"] == dc.SETUP_STEP and e["outcome"] == "fail" and not timed_out for e in entries):
        setup_entry = next(e for e in entries if e["name"] == dc.SETUP_STEP)
        for line in setup_failure_lines(setup_entry.get("exit_code")):
            print(line)
    if timed_out:
        dc.eprint("error: the gate timed out after %g min; the running step was killed" % minutes)
    print("\nresult  : %s -> %s" % ("PASS" if ok else "FAIL", dc.GATE_RESULT_PATH))

    exit_code = dc.EXIT_OK if ok else dc.EXIT_TIMEOUT if timed_out else dc.EXIT_FAIL
    rec = result["e2e"]
    if rec["required"]:
        print("e2e     : %s (%s: %s)" % (rec["outcome"], rec["selection"], ", ".join(rec["specs"]) or "whole suite"))
    if args.e2e_only and not rec["required"]:
        print("e2e     : nothing to run, this branch changes no UI path or e2e spec")
        return dc.EXIT_OK
    if args.e2e_only and not args.no_publish:
        print("note    : --e2e-only; the e2e record is published, the result is partial and the gate does not trust it")
    elif partial:
        print("note    : --only/--skip/--no-setup used; this result is partial and is not published or trusted")
    if (not partial or args.e2e_only) and not args.no_publish:
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
