#!/usr/bin/env python3
"""Prove preflight.py blocks what it claims to block, and passes what it should.

`auth-setup` refuses to run on a repository `tech-stack-setup` has not prepared.
That refusal is the whole point of the script, so it needs the same treatment
every other gate in this repo got: a case that makes it fire, and a case that
makes it stay quiet. A guard nobody has watched fail is indistinguishable from
one that always exits 0 — and this repo has shipped that exact thing five times.

Each case builds a real temporary git repository, because the script shells out
to `git rev-parse` and stats real paths. A mocked filesystem would not exercise
the part that breaks.

Run:  python3 tools/test_preflight.py
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREFLIGHT = (ROOT / "claude/plugins/project-setup/skills/tech-stack-setup"
             / "assets/preflight.py")


def build(kind: str) -> pathlib.Path:
    """A temp directory in one of the states the script has to tell apart."""
    d = pathlib.Path(tempfile.mkdtemp())
    if kind == "not-a-repo":
        return d
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    if kind == "empty-repo":
        return d
    if kind in ("stack-only", "stack-and-auth"):
        (d / "docs/specs").mkdir(parents=True)
        (d / "docs/specs/stack-profile.md").write_text("# Stack Profile\n")
        (d / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")
        (d / "packages").mkdir()
    if kind == "stack-and-auth":
        (d / "packages/auth").mkdir(parents=True)
    if kind == "half-built":
        # A workspace exists but the profile does not: tech-stack-setup was
        # interrupted, or someone hand-rolled a monorepo. This must still block
        # — the profile is what names the stack auth-setup targets.
        (d / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")
        (d / "packages").mkdir()
    return d


def run(cwd: pathlib.Path, *args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(PREFLIGHT), *args],
                       cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


# (name, repo state, args, expected exit, substring the output must contain)
CASES = [
    ("empty repo blocks auth-setup", "empty-repo",
     ["--require", "stack", "--for-skill", "auth-setup"], 1, "tech-stack-setup"),
    ("empty repo names the missing profile", "empty-repo",
     ["--require", "stack"], 1, "docs/specs/stack-profile.md is missing"),
    ("not a git repo blocks", "not-a-repo",
     ["--require", "stack"], 1, "not a git repository"),
    ("workspace without a profile still blocks", "half-built",
     ["--require", "stack"], 1, "stack-profile.md is missing"),
    ("a set-up repo passes", "stack-only",
     ["--require", "stack"], 0, "preflight OK"),
    ("missing packages/auth blocks a downstream skill", "stack-only",
     ["--require", "stack", "--require", "auth"], 1, "Run the `auth-setup`"),
    ("stack + auth passes", "stack-and-auth",
     ["--require", "stack", "--require", "auth"], 0, "preflight OK"),
    # A guard invoked with no requirement must not look like a pass.
    ("no --require is an error, not a pass", "stack-only",
     [], 2, "nothing was asserted"),
    ("an unknown requirement is rejected", "stack-only",
     ["--require", "nonexistent"], 2, "invalid choice"),
]


def main() -> int:
    failures = 0
    for name, state, args, want_code, want_text in CASES:
        d = build(state)
        try:
            code, out = run(d, *args)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        ok = code == want_code and want_text in out
        if ok:
            print(f"PASS  {name:48s} exit {code}")
        else:
            failures += 1
            print(f"FAIL  {name:48s} exit {code} (wanted {want_code}), "
                  f"looked for {want_text!r}")
            print("      " + out.strip().replace("\n", "\n      ")[:400])
    print(f"\n{len(CASES) - failures}/{len(CASES)} cases behaved as specified")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
