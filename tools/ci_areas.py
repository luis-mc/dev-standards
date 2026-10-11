#!/usr/bin/env python3
"""Decide which spec-lint areas a change touches (DS43, TC1, DS44).

spec-lint is split into one job per area. The first job runs this script, which
reads the changed paths and writes GitHub outputs (appended to $GITHUB_OUTPUT,
and printed):

    specs, delivery, artifacts, profiles   true | false
    mutants                                true | false

Area map (first matching rule wins; see RULES):

  specs      spec_check, templates, AUTHSPEC and ARTIFACTSPEC numbering and
             content: the specs' references/, the spec-new template, the
             spec-check script, the Stack Profile template, authspec_check.py,
             route-ratelimit-map.json and their tests.
  delivery   the tech-stack-setup preflight and everything under
             assets/tooling/ (delivery scripts, git hooks, ci.yml templates),
             the delivery/cleanup/prune/change-notes/preflight tests.
  artifacts  claude/plugins/artifacts/ (renderer, commands, hooks, templates)
             and their tests; ARTIFACTSPEC itself counts as specs.
  profiles   every SKILL.md, the claude-setup assets, the architect agent and
             test_model_profiles.py.

Shared paths run every area: this workflow, this script and its test,
tools/change-notes.json, any tools/*common*. Fail safe: a path under tools/ or
claude/ that no rule names also runs every area.

Nothing heavy runs for: everything under docs/ (docs/specs/changes notes are
checked by the always-on `change-notes` job on pull requests, not by an area),
plugin.json manifests (same job), the tech-stack-setup catalog, other
workflows (they have their own triggers), and files outside tools/ and claude/.

Mutants (TC1): true only when the change touches the delivery scripts, the git
hooks, or test_delivery_gate.py / test_delivery_cleanup.py, or when the caller
forces it (nightly). Otherwise the suites run with --no-mutants.

Events: pull_request diffs `base...head`; push diffs the pushed range
`before..head`; workflow_dispatch, schedule and any range that cannot be read
run every area. `--skip` (DS44: a push to main that differs from the tested PR
head only under docs/artifacts/, decided by scripts/delivery/ci_skip_check.py)
turns every output off.

Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

AREAS = ("specs", "delivery", "artifacts", "profiles")
ALL = frozenset(AREAS)
NONE: frozenset[str] = frozenset()

PS = "claude/plugins/project-setup/skills"
TS = PS + "/tech-stack-setup"
TOOLING = TS + "/assets/tooling"
DELIVERY_SCRIPTS = TOOLING + "/shared/scripts/delivery/"
HOOKS = TOOLING + "/shared/.githooks/"
MUTANT_FILES = {"tools/test_delivery_gate.py", "tools/test_delivery_cleanup.py"}

# (regex fullmatch on the repo-relative path with forward slashes, areas).
RULES: list[tuple[str, frozenset[str]]] = [
    # shared: every area
    (r"\.github/workflows/spec-lint\.yml", ALL),
    (r"tools/ci_areas\.py", ALL),
    (r"tools/test_ci_areas\.py", ALL),
    (r"tools/change-notes\.json", ALL),
    (r"tools/[^/]*common[^/]*", ALL),
    # nothing heavy
    (r"docs/.*", NONE),
    (r"claude/plugins/[^/]+/\.claude-plugin/.*", NONE),
    (re.escape(TS) + r"/assets/catalog/.*", NONE),
    (re.escape(TS) + r"/assets/check_stack\.py", NONE),
    (r"tools/template_build_check\.py", NONE),
    # specs
    (re.escape(TS) + r"/references/.*", frozenset({"specs"})),
    (re.escape(PS) + r"/auth-setup/references/.*", frozenset({"specs"})),
    (r"claude/plugins/artifacts/references/.*", frozenset({"specs"})),
    (r"claude/plugins/specs/skills/spec-new/assets/.*", frozenset({"specs"})),
    (r"claude/plugins/specs/skills/spec-check/assets/.*", frozenset({"specs"})),
    (re.escape(TS) + r"/assets/stack-profile\.md", frozenset({"specs"})),
    (r"tools/(spec_check|authspec_check|test_spec_check|test_authspec_check)\.py",
     frozenset({"specs"})),
    (r"tools/route-ratelimit-map\.json", frozenset({"specs"})),
    # profiles (SKILL.md anywhere under the plugins, before the area folders)
    (r"claude/plugins/.*/SKILL\.md", frozenset({"profiles"})),
    (re.escape(PS) + r"/claude-setup/assets/.*", frozenset({"profiles"})),
    (r"claude/plugins/agents/agents/.*", frozenset({"profiles"})),
    (r"tools/test_model_profiles\.py", frozenset({"profiles"})),
    # artifacts
    (r"claude/plugins/artifacts/.*", frozenset({"artifacts"})),
    (r"tools/(test_render_artifacts|test_project_artifacts[a-z_]*|convert_interim_record)\.py",
     frozenset({"artifacts"})),
    # delivery
    (re.escape(TOOLING) + r"/.*", frozenset({"delivery"})),
    (re.escape(TS) + r"/assets/preflight\.py", frozenset({"delivery"})),
    (r"tools/(test_delivery_[a-z]+|test_artifact_prune|test_change_notes|test_preflight)\.py",
     frozenset({"delivery"})),
]
COMPILED = [(re.compile(p), a) for p, a in RULES]


def norm(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def areas_for(path: str) -> frozenset[str]:
    """The areas one changed path runs. Unknown under tools/ or claude/ is all."""
    path = norm(path)
    for rx, areas in COMPILED:
        if rx.fullmatch(path):
            return areas
    if path.startswith(("tools/", "claude/")):
        return ALL
    return NONE


def touches_mutants(path: str) -> bool:
    path = norm(path)
    return (path.startswith(DELIVERY_SCRIPTS) or path.startswith(HOOKS)
            or path in MUTANT_FILES)


def classify(paths: list[str], *, run_all: bool = False, force_mutants: bool = False,
             skip: bool = False) -> dict[str, bool]:
    """The outputs for a set of changed paths."""
    if skip:
        return {**{a: False for a in AREAS}, "mutants": False}
    if run_all:
        return {**{a: True for a in AREAS}, "mutants": force_mutants}
    hit: set[str] = set()
    for p in paths:
        hit |= areas_for(p)
    out = {a: a in hit for a in AREAS}
    mutants = force_mutants or any(touches_mutants(p) for p in paths)
    out["mutants"] = mutants and out["delivery"]
    return out


def changed_paths(event: str, base: str, head: str) -> list[str] | None:
    """Changed paths for the event, or None when every area must run."""
    if event not in ("pull_request", "push"):
        return None
    if not base or not head or set(base) == {"0"}:
        return None
    rng = f"{base}...{head}" if event == "pull_request" else f"{base}..{head}"
    try:
        proc = subprocess.run(["git", "diff", "--name-only", "--no-renames", rng],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.splitlines() if p]


def emit(out: dict[str, bool], note: str) -> None:
    lines = [f"{k}={'true' if v else 'false'}" for k, v in out.items()]
    print(f"ci_areas: {note}")
    print("\n".join(lines))
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Which spec-lint areas does a change touch?")
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    ap.add_argument("--base", default="")
    ap.add_argument("--head", default="")
    ap.add_argument("--mutants", default="", help="true forces the mutation passes (nightly)")
    ap.add_argument("--skip", default="", help="true: DS44 main-after-merge skip, run nothing")
    args = ap.parse_args(argv)

    skip = truthy(args.skip)
    force = truthy(args.mutants)
    paths = None if skip else changed_paths(args.event, args.base, args.head)
    if skip:
        emit(classify([], skip=True),
             "skipped, main differs from the tested PR head only in ignored paths")
    elif paths is None:
        emit(classify([], run_all=True, force_mutants=force),
             f"event {args.event or '?'} (or an unreadable range) runs every area")
    else:
        emit(classify(paths, force_mutants=force), f"{len(paths)} changed path(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
