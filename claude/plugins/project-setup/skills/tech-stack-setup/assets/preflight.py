#!/usr/bin/env python3
"""Assert a repository is far enough along for a setup skill to run.

Every skill in `luismc-project-setup` after `tech-stack-setup` builds on what
an earlier one produced. `auth-setup` cannot add `packages/auth` to a directory
with no workspace, no `packages/`, and no Stack Profile telling it which stack
it is targeting — and the failure mode if it tries is the expensive one: it
invents a plausible structure, the user accepts it, and the repo now has two
competing ideas of its own layout.

So the ordering contract is a script rather than a sentence in a SKILL.md. A
prose precondition is advisory; a non-zero exit is not.

Usage:
    python3 preflight.py --require stack
    python3 preflight.py --require stack --require auth

Exit codes:
    0  every requirement is satisfied
    1  at least one is not — stdout names the skill to run first
    2  the arguments were wrong (unknown requirement, no --require given)

Adding a requirement: add an entry to REQUIREMENTS. Each names the skill that
satisfies it, so the failure message can tell the user what to run rather than
only what is missing. That is the whole point of the `fix` field — "packages/auth
not found" is a symptom; "run auth-setup first" is an instruction.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Requirement:
    """One precondition, and the skill that produces it."""

    name: str
    summary: str
    fix: str
    # Paths that must all exist, relative to the repo root.
    paths: list[str] = field(default_factory=list)
    # At least one of these must exist. Empty means no such constraint.
    any_paths: list[str] = field(default_factory=list)


REQUIREMENTS: dict[str, Requirement] = {
    "stack": Requirement(
        name="stack",
        summary="the repository has been set up to STACKSPEC",
        fix="tech-stack-setup",
        # The Stack Profile is the canonical marker: STACKSPEC §23 makes it
        # mandatory, AUTHSPEC §2.1 resolves the stack through it, and it is the
        # last thing tech-stack-setup writes. Its presence means that skill ran
        # to completion rather than partway.
        paths=["docs/specs/stack-profile.md", "pnpm-workspace.yaml"],
        any_paths=["packages", "apps"],
    ),
    "auth": Requirement(
        name="auth",
        summary="the authentication package exists",
        fix="auth-setup",
        paths=["packages/auth"],
    ),
}


def repo_root() -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return Path(out.stdout.strip())


def check(req: Requirement, root: Path) -> list[str]:
    """Every unmet condition in `req`, as human-readable strings."""
    missing = [p for p in req.paths if not (root / p).exists()]
    out = [f"{p} is missing" for p in missing]
    if req.any_paths and not any((root / p).exists() for p in req.any_paths):
        out.append("none of " + ", ".join(req.any_paths) + " exists")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assert a repo is ready for a project-setup skill.")
    ap.add_argument(
        "--require", action="append", default=[], metavar="NAME",
        choices=sorted(REQUIREMENTS),
        help="requirement to assert; repeatable. Choices: "
             + ", ".join(sorted(REQUIREMENTS)))
    ap.add_argument("--for-skill", default="this skill", metavar="NAME",
                    help="name of the skill being guarded, for the message")
    args = ap.parse_args()

    if not args.require:
        print("preflight: no --require given, so nothing was asserted. That is "
              "an error and not a pass: a guard that checks nothing must not "
              "report the same success as one that checked and found the repo "
              "ready.", file=sys.stderr)
        return 2

    root = repo_root()
    if root is None:
        print("BLOCKED: this is not a git repository.\n\n"
              "  Run `git init` first, then `tech-stack-setup`.")
        return 1

    failures: list[tuple[Requirement, list[str]]] = []
    for name in args.require:
        req = REQUIREMENTS[name]
        problems = check(req, root)
        if problems:
            failures.append((req, problems))

    if not failures:
        checked = ", ".join(args.require)
        print(f"preflight OK — {checked} satisfied in {root}")
        return 0

    print(f"BLOCKED: {args.for_skill} cannot run in {root}\n")
    for req, problems in failures:
        print(f"  Requires: {req.summary}")
        for p in problems:
            print(f"    - {p}")
        print(f"  Run the `{req.fix}` skill first.\n")
    print("Nothing has been written. Generating on top of a repository that is "
          "not set up produces a second, invented layout competing with the "
          "real one, which is far more work to unpick than running the skills "
          "in order.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
