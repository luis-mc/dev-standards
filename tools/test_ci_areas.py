#!/usr/bin/env python3
"""Tests for tools/ci_areas.py (DS43, TC1, DS44). Plain python, no dependencies.

Run:  python3 tools/test_ci_areas.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_areas as ca  # noqa: E402

TS = "claude/plugins/project-setup/skills/tech-stack-setup"
FAILS: list[str] = []


def hit(paths: list[str], **kw) -> set[str]:
    out = ca.classify(paths, **kw)
    return {a for a in ca.AREAS if out[a]}


def check(name: str, got, want) -> None:
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")


ALL = set(ca.AREAS)


def mflags_early(path_list):
    out = ca.classify(path_list)
    return tuple(out[k] for k in ("mutants", "mutants_gate", "mutants_cleanup", "mutants_notes"))


# one path per area
for path, want in [
    (f"{TS}/references/invariants.md", {"specs"}),
    ("claude/plugins/project-setup/skills/auth-setup/references/authentication.md", {"specs"}),
    ("claude/plugins/artifacts/references/artifactspec.md", {"specs"}),
    ("claude/plugins/specs/skills/spec-new/assets/spec-template.md", {"specs"}),
    ("claude/plugins/specs/skills/spec-check/assets/spec_check.py", {"specs"}),
    (f"{TS}/assets/stack-profile.md", {"specs"}),
    ("tools/authspec_check.py", {"specs"}),
    ("tools/test_spec_check.py", {"specs"}),
    ("tools/route-ratelimit-map.json", {"specs"}),
    (f"{TS}/assets/preflight.py", {"delivery"}),
    (f"{TS}/assets/tooling/shared/scripts/delivery/join.py", {"delivery"}),
    (f"{TS}/assets/tooling/ts/.github/workflows/ci.yml", {"delivery"}),
    ("tools/test_delivery_gate.py", {"delivery"}),
    ("tools/test_artifact_prune.py", {"delivery"}),
    ("tools/test_delivery_runner.py", {"delivery"}),
    ("tools/test_ci_speedups.py", {"delivery"}),
    ("claude/plugins/delivery/scripts/delivery_ledger.py", {"delivery"}),
    ("tools/test_delivery_hooks.py", {"delivery"}),
    ("tools/test_change_notes.py", {"delivery"}),
    ("tools/test_preflight.py", {"delivery"}),
    ("tools/test_rule_tags.py", {"specs"}),
    ("claude/plugins/artifacts/rules/project-artifacts.md", {"specs", "artifacts"}),
    ("claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/agents-and-integration.md", {"specs", "profiles"}),
    ("claude/plugins/artifacts/scripts/render_artifacts.py", {"artifacts"}),
    ("claude/plugins/artifacts/hooks/hooks.json", {"artifacts"}),
    ("tools/test_project_artifacts_hooks.py", {"artifacts"}),
    ("tools/test_render_artifacts.py", {"artifacts"}),
    ("claude/plugins/audits/skills/security-audit/SKILL.md", {"profiles"}),
    ("claude/plugins/project-setup/skills/claude-setup/assets/model-profiles.json", {"profiles"}),
    ("claude/plugins/agents/agents/architect.md", {"profiles"}),
    ("tools/test_model_profiles.py", {"profiles"}),
    ("claude/plugins/transcript-folds/hooks/transcript_folds.tsx", {"transcript-folds"}),
    ("claude/plugins/transcript-folds/hooks/fold/width.ts", {"transcript-folds"}),
    ("claude/plugins/transcript-folds/hooks/hooks.json", {"transcript-folds"}),
    ("claude/plugins/transcript-folds/tests/width.test.ts", {"transcript-folds"}),
    ("claude/plugins/transcript-folds/types/state.d.ts", {"transcript-folds"}),
]:
    check(f"area of {path}", hit([path]), want)

# shared paths run everything
for path in [".github/workflows/spec-lint.yml", "tools/ci_areas.py", "tools/test_ci_areas.py",
             "tools/change-notes.json", "tools/some_common_helpers.py"]:
    check(f"shared {path}", hit([path]), ALL)

# unknown under tools/ or claude/ runs everything
for path in ["tools/brand_new_script.py", "claude/plugins/specs/skills/spec-new/notes.txt",
             "claude/other/file.txt"]:
    check(f"unknown {path}", hit([path]), ALL)

# nothing heavy
for path in ["docs/artifacts/feature-x.html", "docs/plans/test-cost-train.md",
             "docs/specs/changes/foo.md", "README.md", ".gitignore",
             ".github/workflows/nightly.yml", ".github/workflows/template-build.yml",
             "claude/plugins/artifacts/.claude-plugin/plugin.json",
             "claude/plugins/transcript-folds/.claude-plugin/plugin.json",
             f"{TS}/assets/catalog/tech/data.yaml", f"{TS}/assets/check_stack.py",
             "tools/template_build_check.py"]:
    check(f"none {path}", hit([path]), set())
check("docs-only mix", hit(["docs/a.md", "docs/artifacts/b.html", "README.md"]), set())

# a union, and Windows separators
check("union", hit(["docs/a.md", "tools/test_render_artifacts.py",
                    "tools/test_model_profiles.py"]), {"artifacts", "profiles"})
check("backslashes", hit(["tools\\test_render_artifacts.py"]), {"artifacts"})
check("transcript-folds with a manifest bump and docs",
      hit(["claude/plugins/transcript-folds/.claude-plugin/plugin.json", "docs/a.md"]), set())
check("transcript-folds union",
      hit(["claude/plugins/transcript-folds/hooks/fold/lines.ts", "tools/test_model_profiles.py"]),
      {"transcript-folds", "profiles"})
check("transcript-folds is light advice",
      ca.advice(["claude/plugins/transcript-folds/hooks/fold/lines.ts"]), "light: test locally only")
check("transcript-folds does not turn on mutants",
      mflags_early(["claude/plugins/transcript-folds/hooks/fold/lines.ts"]), (False, False, False, False))
check("empty diff", hit([]), set())

NOMUT = {"mutants": False, "mutants_gate": False, "mutants_cleanup": False,
         "mutants_notes": False}

# mutants
D = f"{TS}/assets/tooling/shared/scripts/delivery/"
TOOL = f"{TS}/assets/tooling"


def mflags(path_list, **kw):
    out = ca.classify(path_list, **kw)
    return tuple(out[k] for k in ("mutants", "mutants_gate", "mutants_cleanup", "mutants_notes"))


T, F = True, False
# (path, (any, gate, cleanup, notes))
for path, want in [
    (D + "cleanup.py", (T, F, T, F)), (D + "delivery_log.py", (T, F, T, F)),
    (D + "branch_gate.py", (T, T, F, F)), (D + "gate_verify.py", (T, T, F, F)),
    (D + "agent_setup.sh", (T, T, F, F)), (D + "train_freeze.py", (T, T, F, F)),
    (D + "join.py", (T, T, T, F)), (D + "fast_guards.py", (T, T, T, F)),
    (D + "delivery_common.py", (T, T, T, T)),
    (D + "change_notes.py", (T, F, F, T)),
    (D + "CONTRACT.md", (F, F, F, F)), (D + "ci_watch.py", (F, F, F, F)),
    (D + "smoke_packaged.py", (F, F, F, F)), (D + "artifact_prune.py", (F, F, F, F)),
    (f"{TOOL}/shared/.githooks/pre-push", (T, T, F, F)),
    (f"{TOOL}/shared/.github/workflows/train-cleanup.yml", (T, F, T, F)),
    (f"{TOOL}/ts/.github/workflows/ci.yml", (T, F, T, F)),
    ("tools/test_delivery_gate.py", (T, T, T, F)),
    ("tools/test_delivery_cleanup.py", (T, F, T, F)),
    ("tools/test_change_notes.py", (T, F, F, T)),
    ("tools/test_delivery_ci.py", (F, F, F, F)),
    (f"{TS}/assets/preflight.py", (F, F, F, F)),
    (f"{TS}/assets/tooling/ts/vitest.config.ts", (F, F, F, F)),
    ("tools/test_render_artifacts.py", (F, F, F, F)),
    ("docs/a.md", (F, F, F, F)),
]:
    check(f"mutants {path}", mflags([path]), want)
check("mutants: delivery_log + cleanup test only cleanup",
      mflags([D + "delivery_log.py", "tools/test_delivery_cleanup.py"]), (T, F, T, F))
check("mutants with other changes", mflags(["docs/a.md", D + "join.py"]), (T, T, T, F))
check("forced mutants need delivery work",
      mflags(["tools/test_model_profiles.py"], force_mutants=True), (F, F, F, F))
check("mutants forced with delivery", mflags([D + "x.py"], force_mutants=True), (T, T, T, T))
check("mutants forced run_all", ca.classify([], run_all=True, force_mutants=True),
      {**{a: True for a in ca.AREAS}, "mutants": True, "mutants_gate": True,
       "mutants_cleanup": True, "mutants_notes": True})
check("run_all without force", mflags([], run_all=True), (F, F, F, F))

# main-after-merge skip: nothing runs, even for a shared path
check("skip", ca.classify([".github/workflows/spec-lint.yml"], skip=True),
      {**{a: False for a in ca.AREAS}, **NOMUT})
check("skip beats run_all",
      mflags([], run_all=True, force_mutants=True, skip=True), (F, F, F, F))


# branch advice
check("advice light", ca.advice(["claude/plugins/project-setup/skills/x/SKILL.md", "docs/a.md"]),
      "light: test locally only")
check("advice docs only", ca.advice(["docs/a.md"]), "light: test locally only")
check("advice specs light", ca.advice([f"{TS}/references/invariants.md"]),
      "light: test locally only")
check("advice heavy delivery", ca.advice([f"{TS}/assets/preflight.py"], "DS9-a"),
      "heavy: delivery -> run `gh workflow run spec-lint.yml --ref DS9-a -f areas=delivery`")
check("advice heavy lists touched areas",
      ca.advice(["claude/plugins/artifacts/x.py", "tools/test_model_profiles.py"], "b"),
      "heavy: artifacts -> run `gh workflow run spec-lint.yml --ref b -f areas=artifacts,profiles`")
check("advice shared path is every area, heavy",
      ca.advice(["tools/ci_areas.py"], "b"),
      "heavy: delivery,artifacts -> run `gh workflow run spec-lint.yml --ref b "
      "-f areas=specs,delivery,artifacts,profiles,transcript-folds`")
check("parse_areas order and trim", ca.parse_areas(" profiles,specs "), ["specs", "profiles"])
check("parse_areas empty", ca.parse_areas(""), [])
try:
    ca.parse_areas("x")
    check("parse_areas unknown raises", False, True)
except ValueError:
    pass


# end to end: the CLI, with real git ranges and $GITHUB_OUTPUT
def git(cwd: str, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def cli(cwd: str, *args: str) -> dict[str, str]:
    out = Path(cwd) / "gh_output"
    out.write_text("")
    env = {**os.environ, "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run([sys.executable, str(Path(ca.__file__)), *args], cwd=cwd, env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        FAILS.append(f"cli {args}: exit {proc.returncode}: {proc.stderr}")
    return dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)


def commit(cwd: str, rel: str) -> str:
    p = Path(cwd) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(rel + os.urandom(4).hex())
    git(cwd, "add", "-A", "--", rel)
    git(cwd, "commit", "-qm", rel)
    return git(cwd, "rev-parse", "HEAD")


with tempfile.TemporaryDirectory() as tmp:
    git(tmp, "init", "-q")
    base = commit(tmp, "README.md")
    docs = commit(tmp, "docs/artifacts/x.html")
    prof = commit(tmp, "tools/test_model_profiles.py")
    dgate = commit(tmp, "tools/test_delivery_gate.py")
    none = {"specs": "false", "delivery": "false", "artifacts": "false", "profiles": "false",
            "transcript-folds": "false", "mutants": "false", "mutants_gate": "false", "mutants_cleanup": "false",
            "mutants_notes": "false"}
    every = {**none, "specs": "true", "delivery": "true", "artifacts": "true",
             "profiles": "true", "transcript-folds": "true"}
    allmut = {"mutants": "true", "mutants_gate": "true", "mutants_cleanup": "true",
              "mutants_notes": "true"}
    gatemut = {"mutants": "true", "mutants_gate": "true", "mutants_cleanup": "true"}
    check("cli pr docs-only",
          cli(tmp, "--event", "pull_request", "--base", base, "--head", docs), none)
    check("cli pr profiles",
          cli(tmp, "--event", "pull_request", "--base", base, "--head", prof),
          {**none, "profiles": "true"})
    tf = commit(tmp, "claude/plugins/transcript-folds/hooks/fold/lines.ts")
    check("cli pr transcript-folds",
          cli(tmp, "--event", "pull_request", "--base", dgate, "--head", tf),
          {**none, "transcript-folds": "true"})
    check("cli push range", cli(tmp, "--event", "push", "--base", docs, "--head", prof),
          {**none, "profiles": "true"})
    check("cli push delivery mutants",
          cli(tmp, "--event", "push", "--base", prof, "--head", dgate),
          {**none, "delivery": "true", **gatemut})
    check("cli dispatch on the default branch runs everything (no origin/main)",
          cli(tmp, "--event", "workflow_dispatch"), every)
    check("cli dispatch override",
          cli(tmp, "--event", "workflow_dispatch", "--areas", "delivery, profiles"),
          {**none, "delivery": "true", "profiles": "true"})
    check("cli dispatch override of one area ignores the diff",
          cli(tmp, "--event", "workflow_dispatch", "--areas", "specs"),
          {**none, "specs": "true"})
    check("cli dispatch override with mutants",
          cli(tmp, "--event", "workflow_dispatch", "--areas", "delivery", "--mutants", "true"),
          {**none, "delivery": "true", **allmut})
    check("areas override only applies to dispatch",
          cli(tmp, "--event", "schedule", "--areas", "specs"), every)
    bad = subprocess.run([sys.executable, str(Path(ca.__file__)), "--event", "workflow_dispatch",
                          "--areas", "nope"], cwd=tmp, capture_output=True, text=True)
    check("cli dispatch bad area exits 2", bad.returncode, 2)
    # dispatch with no override: diff against origin/main, not everything
    git(tmp, "branch", "feature", prof)
    git(tmp, "update-ref", "refs/remotes/origin/main", docs)
    git(tmp, "checkout", "-q", "feature")
    check("cli dispatch diffs the branch against the default branch",
          cli(tmp, "--event", "workflow_dispatch"), {**none, "profiles": "true"})
    check("cli dispatch --head names the branch tip",
          cli(tmp, "--event", "workflow_dispatch", "--head", dgate),
          {**none, "profiles": "true", "delivery": "true", **gatemut})
    git(tmp, "update-ref", "refs/remotes/origin/main", prof)
    check("cli dispatch on the default branch tip runs everything",
          cli(tmp, "--event", "workflow_dispatch"), every)
    git(tmp, "update-ref", "refs/remotes/origin/main", docs)

    def advice_cli(*a: str) -> str:
        return subprocess.run([sys.executable, str(Path(ca.__file__)), "--branch-advice", *a],
                              cwd=tmp, capture_output=True, text=True).stdout.strip()

    check("cli advice from the branch diff", advice_cli("--branch", "f"),
          "light: test locally only")
    git(tmp, "checkout", "-q", dgate)
    check("cli advice heavy from the diff", advice_cli("--branch", "DS1-x"),
          "heavy: delivery -> run `gh workflow run spec-lint.yml --ref DS1-x "
          "-f areas=delivery,profiles`")
    check("cli advice with paths", advice_cli("--branch", "b", "docs/a.md"),
          "light: test locally only")
    check("cli schedule nightly", cli(tmp, "--event", "schedule", "--mutants", "true"),
          {**every, **allmut})
    check("cli push new branch (zero before)",
          cli(tmp, "--event", "push", "--base", "0" * 40, "--head", dgate), every)
    check("cli unreadable range",
          cli(tmp, "--event", "pull_request", "--base", "f" * 40, "--head", dgate), every)
    check("cli main-after-merge skip",
          cli(tmp, "--event", "push", "--base", base, "--head", dgate, "--skip", "true"), none)
    check("cli skip=false still runs",
          cli(tmp, "--event", "push", "--base", docs, "--head", prof, "--skip", "false"),
          {**none, "profiles": "true"})

# the workflow wires the outputs the script writes
wf = (Path(__file__).resolve().parent.parent / ".github/workflows/spec-lint.yml").read_text(
    encoding="utf-8")
for area in ca.AREAS:
    check(f"workflow gates job {area}", f"if: needs.areas.outputs.{area} == 'true'" in wf, True)
check("workflow concurrency",
      "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in wf, True)
check("workflow dispatch areas input", "areas:" in wf and "--areas" in wf, True)
for suite in ca.SUITE_MUTANTS:
    check(f"workflow wires mutants_{suite}",
          f"needs.areas.outputs.mutants_{suite}" in wf, True)
check("workflow runs the gate as 4 shards", "--shard ${{ matrix.shard }}/4" in wf, True)

if FAILS:
    print("FAILED:\n  " + "\n  ".join(FAILS))
    sys.exit(1)
print("test_ci_areas: all checks passed")
