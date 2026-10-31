#!/usr/bin/env python3
"""Decide which spec-lint areas a change touches (DS43, TC1, DS44).

spec-lint is split into one job per area. The first job runs this script, which
reads the changed paths and writes GitHub outputs (appended to $GITHUB_OUTPUT,
and printed):

    specs, delivery, artifacts, profiles, transcript-folds, docs   true | false
    mutants                                true | false  (any suite below)
    mutants_gate, mutants_cleanup, mutants_notes   true | false  (TC7, one per suite)

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
  transcript-folds  everything under claude/plugins/transcript-folds/ except
             its .claude-plugin/ manifest (node --test over hooks/fold/*.ts).
  docs       everything under claude/plugins/docs/ except its manifest and
             SKILL.md files (unit tests of the scripts; DOCSPEC under
             references/ also counts as specs).

Shared paths run every area: this workflow, this script and its test,
tools/change-notes.json, any tools/*common*. Fail safe: a path under tools/ or
claude/ that no rule names also runs every area.

Nothing heavy runs for: everything under docs/ (docs/specs/changes notes are
checked by the always-on `change-notes` job on pull requests, not by an area),
plugin.json manifests (same job), the tech-stack-setup catalog, other
workflows (they have their own triggers), and files outside tools/ and claude/.

Mutants (TC1, TC7): one flag per delivery suite that has a mutation pass, true
only when a file that suite tests changes (see SUITE_MUTANTS), or when the
caller forces it (nightly, the `mutants` dispatch input). `mutants` is true when
any of them is. Otherwise that suite runs with --no-mutants.

Events: pull_request diffs `base...head`; push diffs the pushed range
`before..head`; schedule and any range that cannot be read run every area.
workflow_dispatch (DS49) runs the areas named by `--areas` (comma-separated
subset of specs,delivery,artifacts,profiles,transcript-folds,docs); with no override it diffs the
branch against the default branch (`origin/main...head`) and runs what that
touches, and runs every area only when the branch is the default branch itself
or the diff cannot be read.

Branch advice (DS49): `--branch-advice [paths...]` prints whether a change wants
a branch CI run. HEAVY areas (delivery, artifacts: local suites over about
three minutes on Windows) say "heavy: ... -> run `gh workflow run spec-lint.yml
--ref <branch> -f areas=...`"; anything else says "light: test locally only".
With no paths it diffs the current branch against origin/main. `--skip` (DS44: a push to main that differs from the tested PR
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

AREAS = ("specs", "delivery", "artifacts", "profiles", "transcript-folds", "docs")
ALL = frozenset(AREAS)
NONE: frozenset[str] = frozenset()
HEAVY = ("delivery", "artifacts")

PS = "claude/plugins/project-setup/skills"
TS = PS + "/tech-stack-setup"
TOOLING = TS + "/assets/tooling"
DELIVERY_SCRIPTS = TOOLING + "/shared/scripts/delivery/"
HOOKS = TOOLING + "/shared/.githooks/"
DS = DELIVERY_SCRIPTS
# TC7: suite -> the files whose change turns its mutation pass on. Derived from
# what each suite copies, imports or mutates. A path ending in "/" is a folder.
SUITE_MUTANTS: dict[str, frozenset[str]] = {
    # test_delivery_gate.py: copies the whole shared tree and mutates these.
    "gate": frozenset({
        "tools/test_delivery_gate.py",
        DS + "agent_setup.sh", DS + "branch_gate.py", DS + "delivery_common.py",
        DS + "fast_guards.py", DS + "gate_verify.py", DS + "join.py",
        DS + "runner_health.py", DS + "tools.json", DS + "train_freeze.py",
        HOOKS,
    }),
    # test_delivery_cleanup.py: DELIVERY_FILES plus join.py (calls cleanup), the
    # train-cleanup.yml and ts ci.yml it checks, and the gate suite's harness.
    "cleanup": frozenset({
        "tools/test_delivery_cleanup.py", "tools/test_delivery_gate.py",
        DS + "delivery_common.py", DS + "fast_guards.py", DS + "delivery_log.py",
        DS + "cleanup.py", DS + "join.py",
        TOOLING + "/shared/.github/workflows/train-cleanup.yml",
        TOOLING + "/ts/.github/workflows/ci.yml",
    }),
    # test_change_notes.py: copies delivery_common.py and change_notes.py.
    "notes": frozenset({
        "tools/test_change_notes.py", DS + "delivery_common.py", DS + "change_notes.py",
    }),
}
MUTANT_KEYS = {suite: "mutants_" + suite for suite in SUITE_MUTANTS}

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
    # this repository's .claude/ settings and suites: test_session_guard.py (specs) reads them (DS91)
    (r"\.claude/(settings|suites)\.json", frozenset({"specs"})),
    # rule files shipped to projects: tools/test_rule_tags.py (specs) checks their tags
    (r"tools/test_rule_tags\.py", frozenset({"specs"})),
    (r"claude/plugins/artifacts/rules/.*", frozenset({"specs", "artifacts"})),
    (re.escape(PS) + r"/claude-setup/assets/\.claude/rules/.*", frozenset({"specs", "profiles"})),
    # profiles (SKILL.md anywhere under the plugins, before the area folders)
    (r"claude/plugins/.*/SKILL\.md", frozenset({"profiles"})),
    (re.escape(PS) + r"/claude-setup/assets/.*", frozenset({"profiles"})),
    (r"claude/plugins/agents/agents/.*", frozenset({"profiles"})),
    (r"tools/test_model_profiles\.py", frozenset({"profiles"})),
    (r"tools/test_claude_setup_plugins\.py", frozenset({"profiles"})),
    (r"\.claude-plugin/marketplace\.json", frozenset({"profiles"})),
    # transcript-folds (its .claude-plugin/ manifest is matched above: nothing heavy)
    (r"claude/plugins/transcript-folds/.*", frozenset({"transcript-folds"})),
    # docs (SKILL.md and the manifest are matched above)
    (r"claude/plugins/docs/references/.*", frozenset({"specs", "docs"})),
    (r"claude/plugins/docs/.*", frozenset({"docs"})),
    # artifacts
    (r"claude/plugins/artifacts/.*", frozenset({"artifacts"})),
    (r"tools/(test_render_artifacts|test_project_artifacts[a-z_]*|convert_interim_record)\.py",
     frozenset({"artifacts"})),
    # delivery
    (r"claude/plugins/delivery/.*", frozenset({"delivery"})),
    (re.escape(TOOLING) + r"/.*", frozenset({"delivery"})),
    (re.escape(TS) + r"/assets/preflight\.py", frozenset({"delivery"})),
    (r"tools/(test_delivery_[a-z]+|test_artifact_prune|test_change_notes|test_preflight|test_smoke_packaged|test_ci_speedups)\.py",
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


def touches_mutants(path: str, suite: str) -> bool:
    """Does a change to this path turn on that suite's mutation pass?"""
    path = norm(path)
    return any(path == f or (f.endswith("/") and path.startswith(f))
               for f in SUITE_MUTANTS[suite])


def mutant_flags(paths: list[str], force: bool, delivery: bool) -> dict[str, bool]:
    out = {key: delivery and (force or any(touches_mutants(p, s) for p in paths))
           for s, key in MUTANT_KEYS.items()}
    return {"mutants": any(out.values()), **out}


def classify(paths: list[str], *, run_all: bool = False, force_mutants: bool = False,
             skip: bool = False) -> dict[str, bool]:
    """The outputs for a set of changed paths."""
    if skip:
        return {**{a: False for a in AREAS}, **mutant_flags([], False, False)}
    if run_all:
        return {**{a: True for a in AREAS}, **mutant_flags([], force_mutants, True)}
    hit: set[str] = set()
    for p in paths:
        hit |= areas_for(p)
    out = {a: a in hit for a in AREAS}
    out.update(mutant_flags(paths, force_mutants, out["delivery"]))
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


def parse_areas(value: str) -> list[str]:
    """Validate a comma-separated area list; unknown names are an error."""
    names = [v.strip().lower() for v in value.split(",") if v.strip()]
    bad = [n for n in names if n not in ALL]
    if bad:
        raise ValueError(f"unknown area(s) {','.join(bad)}; choose from {','.join(AREAS)}")
    return [a for a in AREAS if a in names]


def git_out(*args: str) -> str | None:
    try:
        proc = subprocess.run(["git", *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def branch_paths(default_branch: str, head: str = "HEAD") -> list[str] | None:
    """Paths the branch changed against the default branch, None when unreadable
    or when the branch is the default branch (nothing to compare)."""
    ref = f"origin/{default_branch}"
    tip, base = git_out("rev-parse", head), git_out("rev-parse", ref)
    if not tip or not base or tip == base:
        return None
    out = git_out("diff", "--name-only", "--no-renames", f"{ref}...{head}")
    return None if out is None else [p for p in out.splitlines() if p]


def advice(paths: list[str], branch: str = "<branch>") -> str:
    """Whether a branch run is wanted for these changed files."""
    out = classify(paths)
    touched = [a for a in AREAS if out[a]]
    heavy = [a for a in HEAVY if out[a]]
    if not heavy:
        return "light: test locally only"
    return (f"heavy: {','.join(heavy)} -> run `gh workflow run spec-lint.yml "
            f"--ref {branch} -f areas={','.join(touched)}`")


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
    ap.add_argument("--areas", default=None,
                    help="workflow_dispatch override: comma-separated areas to run")
    ap.add_argument("--default-branch", default="main",
                    help="dispatch with no --areas diffs the branch against origin/<this>")
    ap.add_argument("--branch-advice", action="store_true",
                    help="print whether the given paths (default: this branch's diff) want a branch run")
    ap.add_argument("--branch", default="", help="branch name for --branch-advice output")
    ap.add_argument("paths", nargs="*", help="changed files for --branch-advice")
    args = ap.parse_args(argv)

    if args.branch_advice:
        name = args.branch or git_out("rev-parse", "--abbrev-ref", "HEAD") or "<branch>"
        paths = args.paths or branch_paths(args.default_branch)
        if paths is None:
            print("heavy: unreadable diff, treat as every area -> run `gh workflow run "
                  f"spec-lint.yml --ref {name} -f areas={','.join(AREAS)}`")
            return 0
        print(advice(paths, name))
        return 0

    skip = truthy(args.skip)
    force = truthy(args.mutants)
    paths = None if skip else changed_paths(args.event, args.base, args.head)
    if not skip and args.event == "workflow_dispatch" and (args.areas or "").strip():
        try:
            chosen = parse_areas(args.areas)
        except ValueError as exc:
            print(f"ci_areas: {exc}", file=sys.stderr)
            return 2
        out = {a: a in chosen for a in AREAS}
        out.update(mutant_flags([], force, out["delivery"]))
        emit(out, f"dispatch override: {','.join(chosen)}")
        return 0
    if not skip and args.event == "workflow_dispatch":
        paths = branch_paths(args.default_branch, args.head or "HEAD")
    if skip:
        emit(classify([], skip=True),
             "skipped, main differs from the tested PR head only in ignored paths")
    elif paths is None:
        emit(classify([], run_all=True, force_mutants=force),
             f"event {args.event or '?'} (or an unreadable range, or the default "
             "branch) runs every area")
    else:
        emit(classify(paths, force_mutants=force), f"{len(paths)} changed path(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
