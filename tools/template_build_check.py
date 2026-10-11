#!/usr/bin/env python3
"""Compile and run the Go, Rust and .NET tooling starters in a throwaway product.

The starters under claude/plugins/project-setup/skills/tech-stack-setup/assets/
tooling/<track>/ are written to be dropped into a generated repository. Nothing
else in this repository compiles them, so a typo in a guard or a bad setup
command in gate.json would ship to every product generated afterwards. This
script builds a minimal product around one track's template and checks that:

  1. the setup commands from the template's own gate.json pass;
  2. the gate's typecheck step (and, for Rust, the lint step) passes;
  3. the gate's guards step compiles, runs the guard and passes on a clean tree;
  4. the guard FAILS when a conflict marker is planted in a scanned file (a
     guard nobody has watched fail is indistinguishable from one that always
     passes);
  5. the guard PASSES when the marker sits inside a nested directory that has
     its own .git (another checkout, such as an agent's worktree), and fails
     again once that .git is removed (so the pass is the skip, not blindness);
  6. the guard reports a planted marker in a nested directory with `/`
     separators on every OS (a starter that prints the platform's own
     backslashes fails this on Windows; CI runs the check on windows-latest
     as well);
  7. the setup commands FAIL when the lockfile is stale, and pass again once it
     is restored.

Commands are taken from the template's gate.json, not hard-coded, and run with
`bash -c` from the scaffold root, the way scripts/delivery/agent_setup.sh runs
them.

Usage:  python3 tools/template_build_check.py --track go|rust|dotnet
        [--work-dir DIR] [--keep]

Needs the track's toolchain (go; cargo with clippy; dotnet 8 SDK), git, bash and
network access to fetch one small dependency. Python 3.11+, standard library
only. Exit 0 when every check holds, 1 when any does not, 2 on a setup error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLING = REPO / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling"

# Built from pieces so this file does not contain a marker line itself.
MARKER_START = "<" * 7 + " HEAD"
MARKER_SEP = "=" * 7
MARKER_END = ">" * 7 + " other-branch"
PLANTED = f"a: 1\n{MARKER_START}\nb: 2\n{MARKER_SEP}\nc: 3\n{MARKER_END}\n"

STEP_TIMEOUT_SECONDS = 1500


def find_bash() -> str:
    """bash from PATH; on Windows Git's own, never System32's WSL launcher (a
    bare "bash" finds that one first, and it cannot see Windows paths)."""
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            for rel in ("../bin/bash.exe", "../../bin/bash.exe"):
                cand = (Path(git).resolve().parent / rel).resolve()
                if cand.exists():
                    return str(cand)
    return shutil.which("bash") or "bash"


BASH = find_bash()


class Checker:
    def __init__(self, track: str, root: Path) -> None:
        self.track = track
        self.root = root
        self.failures: list[str] = []
        self.number = 0

    # -- output -----------------------------------------------------------

    def say(self, text: str = "") -> None:
        print(text, flush=True)

    def header(self, title: str) -> None:
        self.number += 1
        self.say()
        self.say(f"[{self.track} step {self.number}] {title}")

    def verdict(self, ok: bool, title: str, detail: str = "") -> bool:
        self.say(f"  result  : {'OK' if ok else 'FAILED'}" + (f" ({detail})" if detail else ""))
        if not ok:
            self.failures.append(f"step {self.number}: {title}")
        return ok

    # -- running ----------------------------------------------------------

    def run(self, command: str, env: dict[str, str] | None = None) -> tuple[int, str]:
        """Run one shell command from the scaffold root, as agent_setup.sh does."""
        full_env = dict(os.environ)
        full_env.update(env or {})
        try:
            done = subprocess.run(
                [BASH, "-c", command],
                cwd=self.root,
                env=full_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=STEP_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as err:
            return 124, f"timed out after {STEP_TIMEOUT_SECONDS}s\n{err.stdout or ''}"
        return done.returncode, done.stdout or ""

    def tail(self, output: str, lines: int = 40) -> None:
        shown = output.rstrip().splitlines()[-lines:]
        self.say("  output (last %d lines):" % len(shown))
        for line in shown:
            self.say("    | " + line)

    def expect_exit(
        self,
        title: str,
        command: str,
        passes: bool,
        env: dict[str, str] | None = None,
        output_has: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Run `command`; expect exit 0 (passes) or non-zero, plus output patterns."""
        self.header(title)
        wanted = "exit 0" if passes else "a non-zero exit"
        if output_has:
            wanted += " and output matching " + ", ".join(repr(p) for p in output_has)
        self.say(f"  expected: {wanted}")
        self.say(f"  command : {command}")
        started = time.monotonic()
        code, output = self.run(command, env)
        took = time.monotonic() - started
        ok = (code == 0) == passes
        missing = [p for p in (output_has or []) if not re.search(p, output)]
        if missing:
            ok = False
        got = f"exit {code}" + (f", output lacks {missing}" if missing else "")
        self.say(f"  got     : {got} in {took:.0f}s")
        self.verdict(ok, title)
        if not ok:
            self.tail(output)
        return ok, output

    def expect_sequence(self, title: str, commands: list[str], passes: bool) -> tuple[bool, str]:
        """Run commands in order. passes: all exit 0. Otherwise: one exits non-zero."""
        self.header(title)
        self.say("  expected: " + ("every command exits 0" if passes else "a command exits non-zero"))
        failed_at = None
        last_output = ""
        for command in commands:
            self.say(f"  command : {command}")
            code, last_output = self.run(command)
            self.say(f"    -> exit {code}")
            if code != 0:
                failed_at = command
                break
        ok = (failed_at is None) == passes
        self.say("  got     : " + ("every command exited 0" if failed_at is None else f"`{failed_at}` failed"))
        self.verdict(ok, title)
        if not ok or (failed_at and not passes):
            self.tail(last_output, 12)
        return ok, last_output

    # -- fixtures ---------------------------------------------------------

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def plant_marker(self) -> Path:
        return self.write("conflicted.yml", PLANTED)

    def plant_other_checkouts(self) -> list[Path]:
        """Two fake other checkouts holding a marker: a worktree (.git file) and
        a submodule-style one (.git directory)."""
        worktree = self.root / ".claude/worktrees/agent-x"
        sub = self.root / "vendored-sub"
        for d in (worktree, sub):
            d.mkdir(parents=True, exist_ok=True)
            (d / "conflicted.yml").write_text(PLANTED, encoding="utf-8", newline="\n")
        (worktree / ".git").write_text("gitdir: /nonexistent/worktrees/agent-x\n", encoding="utf-8")
        (sub / ".git").mkdir(exist_ok=True)
        return [worktree, sub]


def gate_json(track: str) -> dict:
    return json.loads((TOOLING / track / "scripts/delivery/gate.json").read_text(encoding="utf-8"))


def gate_step(gate: dict, name: str) -> str:
    for step in gate["steps"]:
        if step["name"] == name:
            return step["run"]
    sys.exit(f"template_build_check: gate.json has no step named {name!r}")


def new_scaffold(c: Checker) -> None:
    """Copy the track's template into the scaffold and make it a repository."""
    c.say(f"scaffold: {c.root}")
    shutil.copytree(TOOLING / c.track, c.root, dirs_exist_ok=True)
    # The guards find the repository root by its .git, as in a real product.
    subprocess.run(["git", "init", "-q", str(c.root)], check=True)


def guard_checks(c: Checker, guards_cmd: str, ran: list[str], env: dict[str, str] | None = None) -> None:
    """The same five checks for every track, around the gate's own guards command."""
    c.expect_exit("guards pass on a clean tree and the guard really ran", guards_cmd, True, env, ran)

    marker = c.plant_marker()
    c.expect_exit(
        "guards FAIL when a conflict marker is planted in a scanned file",
        guards_cmd, False, env, [r"conflicted\.yml:2:"],
    )
    marker.unlink()

    # STACKSPEC U9: paths are matched and reported with '/' on every OS. The
    # pattern accepts no backslash before the path on its line, so a starter that
    # prints a back-slashed relative path or an absolute `C:` path fails.
    nested = c.write("nested/dir/conflicted.yml", PLANTED)
    c.expect_exit(
        "guards report a planted marker in a nested directory with '/' separators",
        guards_cmd, False, env, [r"(?m)^[^\\\r\n]*nested/dir/conflicted\.yml:2:"],
    )
    nested.unlink()
    nested.parent.rmdir()
    nested.parent.parent.rmdir()

    others = c.plant_other_checkouts()
    c.expect_exit(
        "guards PASS when the marker is inside nested directories with their own .git",
        guards_cmd, True, env, ran,
    )
    (others[0] / ".git").unlink()
    c.expect_exit(
        "control: the same directory WITHOUT .git is scanned, so the guard FAILS",
        guards_cmd, False, env, [r"agent-x/conflicted\.yml:2:"],
    )
    for d in others:
        shutil.rmtree(d)
    c.expect_exit("guards pass again once the planted files are gone", guards_cmd, True, env, ran)


# --------------------------------------------------------------------------
# Go
# --------------------------------------------------------------------------

def check_go(c: Checker) -> None:
    gate = gate_json("go")
    new_scaffold(c)
    c.write("go.mod", "module example.test/throwaway\n\ngo 1.23\n\nrequire github.com/google/uuid v1.6.0\n")
    c.write(
        "internal/id/id.go",
        'package id\n\nimport "github.com/google/uuid"\n\n// New returns a fresh identifier.\n'
        "func New() string { return uuid.NewString() }\n",
    )
    ok, _ = c.expect_exit("scaffold: go mod tidy writes go.sum", "go mod tidy", True)
    if not ok:
        return

    setup = gate["setup"]
    ok, _ = c.expect_sequence("gate.json setup commands pass with a current go.sum", setup, True)
    if not ok:
        return
    c.expect_exit("gate typecheck step passes", gate_step(gate, "typecheck"), True)

    # -count=1 so a cached result cannot hide a planted marker; -v so the
    # output proves the guard ran (the -run filter would also pass on zero tests).
    env = {"GOFLAGS": "-count=1 -v"}
    guard_checks(c, gate_step(gate, "guards"), [r"--- PASS: TestGuardNoConflictMarkers"], env)

    sum_path = c.root / "go.sum"
    original = sum_path.read_text(encoding="utf-8")
    kept = [l for l in original.splitlines(keepends=True) if not re.match(r"github\.com/google/uuid v1\.6\.0 h1:", l)]
    if len(kept) == len(original.splitlines(keepends=True)):
        c.header("make go.sum stale")
        c.verdict(False, "make go.sum stale", "no uuid line found to drop")
        return
    sum_path.write_text("".join(kept), encoding="utf-8", newline="\n")
    c.expect_sequence("gate.json setup commands FAIL when go.sum lacks a required module's line", setup, False)
    sum_path.write_text(original, encoding="utf-8", newline="\n")
    c.expect_sequence("setup commands pass again with go.sum restored", setup, True)


# --------------------------------------------------------------------------
# Rust
# --------------------------------------------------------------------------

def check_rust(c: Checker) -> None:
    gate = gate_json("rust")
    new_scaffold(c)
    c.write("Cargo.toml", '[workspace]\nresolver = "2"\nmembers = ["crates/guards", "crates/app"]\n')
    c.write(
        "crates/app/Cargo.toml",
        '[package]\nname = "app"\nversion = "0.0.0"\nedition = "2021"\npublish = false\n\n'
        '[dependencies]\nitoa = "1"\n',
    )
    c.write(
        "crates/app/src/lib.rs",
        "/// Formats a number.\npub fn show(n: u32) -> String {\n    itoa::Buffer::new().format(n).to_owned()\n}\n",
    )
    # The product commits its lockfile; the gate's setup runs against it.
    ok, _ = c.expect_exit("scaffold: cargo generate-lockfile writes Cargo.lock", "cargo generate-lockfile", True)
    if not ok:
        return

    setup = gate["setup"]
    ok, _ = c.expect_sequence("gate.json setup commands pass with a current Cargo.lock", setup, True)
    if not ok:
        return
    c.expect_exit("gate typecheck step passes", gate_step(gate, "typecheck"), True)
    c.expect_exit("gate lint step passes (clippy -D warnings)", gate_step(gate, "lint"), True)

    guard_checks(
        c, gate_step(gate, "guards"),
        [r"test guard_no_conflict_markers \.\.\. ok", r"1 passed"],
    )

    lock_path = c.root / "Cargo.lock"
    original = lock_path.read_text(encoding="utf-8")
    # A package block ends at a blank line, or at the end of the file.
    stale = re.sub(r'\[\[package\]\]\nname = "itoa"\n.*?(?:\n\n|\Z)', "", original, flags=re.S)
    if stale == original:
        c.header("make Cargo.lock stale")
        c.verdict(False, "make Cargo.lock stale", "no itoa package block found to drop")
        return
    lock_path.write_text(stale, encoding="utf-8", newline="\n")
    c.expect_sequence("gate.json setup commands FAIL when Cargo.lock lacks a dependency", setup, False)
    lock_path.write_text(original, encoding="utf-8", newline="\n")
    c.expect_sequence("setup commands pass again with Cargo.lock restored", setup, True)


# --------------------------------------------------------------------------
# .NET
# --------------------------------------------------------------------------

def check_dotnet(c: Checker) -> None:
    gate = gate_json("dotnet")
    new_scaffold(c)
    c.write("global.json", '{\n  "sdk": { "version": "8.0.100", "rollForward": "latestFeature" }\n}\n')
    # The gate's setup is `restore --locked-mode`, so the product enables lock files.
    c.write(
        "Directory.Build.props",
        "<Project>\n  <PropertyGroup>\n    <RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>\n"
        "  </PropertyGroup>\n</Project>\n",
    )
    ok, _ = c.expect_exit("scaffold: solution with the Guards project", "dotnet new sln -n Throwaway && dotnet sln add tests/Guards/Guards.csproj", True)
    if not ok:
        return
    ok, _ = c.expect_exit("scaffold: restore writes packages.lock.json", "dotnet restore --force-evaluate", True)
    if not ok:
        return

    setup = gate["setup"]
    ok, _ = c.expect_sequence("gate.json setup commands pass with a current lock file", setup, True)
    if not ok:
        return
    c.expect_exit("gate typecheck step passes (build, warnings as errors)", gate_step(gate, "typecheck"), True)

    guard_checks(c, gate_step(gate, "guards"), [r"Passed:\s+1\b"])

    lock_path = c.root / "tests/Guards/packages.lock.json"
    original = lock_path.read_text(encoding="utf-8")
    data = json.loads(original)
    removed = False
    for deps in data["dependencies"].values():
        if "xunit" in deps:
            del deps["xunit"]
            removed = True
    if not removed:
        c.header("make packages.lock.json stale")
        c.verdict(False, "make packages.lock.json stale", "no xunit entry found to drop")
        return
    lock_path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
    c.expect_sequence("gate.json setup commands FAIL when the lock file lacks a dependency", setup, False)
    lock_path.write_text(original, encoding="utf-8", newline="\n")
    c.expect_sequence("setup commands pass again with the lock file restored", setup, True)


CHECKS = {"go": check_go, "rust": check_rust, "dotnet": check_dotnet}
VERSION_COMMANDS = {
    "go": "go version",
    "rust": "cargo --version && rustc --version && cargo clippy --version",
    "dotnet": "dotnet --version",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--track", required=True, choices=sorted(CHECKS))
    parser.add_argument("--work-dir", help="parent directory for the scaffold (default: $RUNNER_TEMP, else the system temp dir)")
    parser.add_argument("--keep", action="store_true", help="keep the scaffold afterwards")
    args = parser.parse_args()

    for tool in ("bash", "git"):
        if shutil.which(tool) is None:
            print(f"template_build_check: {tool} is required and was not found on PATH", file=sys.stderr)
            return 2
    if not (TOOLING / args.track).is_dir():
        print(f"template_build_check: no template at {TOOLING / args.track}", file=sys.stderr)
        return 2

    parent = Path(args.work_dir or os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f"template-build-{args.track}-", dir=parent))
    c = Checker(args.track, root)
    try:
        code, out = c.run(VERSION_COMMANDS[args.track])
        c.say(f"toolchain (exit {code}):\n" + "\n".join("  " + l for l in out.strip().splitlines()))
        if code != 0:
            print(f"template_build_check: the {args.track} toolchain is not installed", file=sys.stderr)
            return 2
        CHECKS[args.track](c)
    finally:
        if args.keep:
            c.say(f"\nscaffold kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)

    c.say()
    if c.failures:
        c.say(f"{args.track}: {len(c.failures)} of {c.number} steps FAILED")
        for line in c.failures:
            c.say("  - " + line)
        return 1
    c.say(f"{args.track}: all {c.number} steps behaved as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
