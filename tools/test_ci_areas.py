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
    ("tools/test_change_notes.py", {"delivery"}),
    ("tools/test_preflight.py", {"delivery"}),
    ("claude/plugins/artifacts/scripts/render_artifacts.py", {"artifacts"}),
    ("claude/plugins/artifacts/hooks/hooks.json", {"artifacts"}),
    ("tools/test_project_artifacts_hooks.py", {"artifacts"}),
    ("tools/test_render_artifacts.py", {"artifacts"}),
    ("claude/plugins/audits/skills/security-audit/SKILL.md", {"profiles"}),
    ("claude/plugins/project-setup/skills/claude-setup/assets/model-profiles.json", {"profiles"}),
    ("claude/plugins/agents/agents/architect.md", {"profiles"}),
    ("tools/test_model_profiles.py", {"profiles"}),
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
             f"{TS}/assets/catalog/tech/data.yaml", f"{TS}/assets/check_stack.py",
             "tools/template_build_check.py"]:
    check(f"none {path}", hit([path]), set())
check("docs-only mix", hit(["docs/a.md", "docs/artifacts/b.html", "README.md"]), set())

# a union, and Windows separators
check("union", hit(["docs/a.md", "tools/test_render_artifacts.py",
                    "tools/test_model_profiles.py"]), {"artifacts", "profiles"})
check("backslashes", hit(["tools\\test_render_artifacts.py"]), {"artifacts"})
check("empty diff", hit([]), set())

# mutants
D = f"{TS}/assets/tooling/shared/scripts/delivery/"
for path, want in [
    (D + "cleanup.py", True), (D + "CONTRACT.md", True),
    (f"{TS}/assets/tooling/shared/.githooks/pre-push", True),
    ("tools/test_delivery_gate.py", True), ("tools/test_delivery_cleanup.py", True),
    ("tools/test_change_notes.py", False), ("tools/test_delivery_ci.py", False),
    (f"{TS}/assets/preflight.py", False),
    (f"{TS}/assets/tooling/ts/vitest.config.ts", False),
    ("tools/test_render_artifacts.py", False),
    ("docs/a.md", False),
]:
    check(f"mutants {path}", ca.classify([path])["mutants"], want)
check("mutants with other changes", ca.classify(["docs/a.md", D + "join.py"])["mutants"], True)
check("forced mutants need delivery work",
      ca.classify(["tools/test_model_profiles.py"], force_mutants=True)["mutants"], False)
check("mutants forced with delivery", ca.classify([D + "x.py"], force_mutants=True)["mutants"], True)
check("mutants forced run_all", ca.classify([], run_all=True, force_mutants=True),
      {**{a: True for a in ca.AREAS}, "mutants": True})
check("run_all without force", ca.classify([], run_all=True)["mutants"], False)

# main-after-merge skip: nothing runs, even for a shared path
check("skip", ca.classify([".github/workflows/spec-lint.yml"], skip=True),
      {**{a: False for a in ca.AREAS}, "mutants": False})
check("skip beats run_all",
      ca.classify([], run_all=True, force_mutants=True, skip=True)["mutants"], False)


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
            "mutants": "false"}
    every = {"specs": "true", "delivery": "true", "artifacts": "true", "profiles": "true",
             "mutants": "false"}
    check("cli pr docs-only",
          cli(tmp, "--event", "pull_request", "--base", base, "--head", docs), none)
    check("cli pr profiles",
          cli(tmp, "--event", "pull_request", "--base", base, "--head", prof),
          {**none, "profiles": "true"})
    check("cli push range", cli(tmp, "--event", "push", "--base", docs, "--head", prof),
          {**none, "profiles": "true"})
    check("cli push delivery mutants",
          cli(tmp, "--event", "push", "--base", prof, "--head", dgate),
          {**none, "delivery": "true", "mutants": "true"})
    check("cli dispatch", cli(tmp, "--event", "workflow_dispatch"), every)
    check("cli schedule nightly", cli(tmp, "--event", "schedule", "--mutants", "true"),
          {**every, "mutants": "true"})
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
check("workflow no-mutants wiring", wf.count("mutants != 'true' && '--no-mutants'"), 3)

if FAILS:
    print("FAILED:\n  " + "\n  ".join(FAILS))
    sys.exit(1)
print("test_ci_areas: all checks passed")
