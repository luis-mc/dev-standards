#!/usr/bin/env python3
"""Prove change_notes.py behaves as CONTRACT.md (U7) says.

Every scenario builds a throwaway git repository holding the delivery scripts
copied from the plugin assets, a minimal gate.json and two specs, then runs
`change_notes.py check` / `fold` in it.

"Every check must be able to fail" is proved two ways: the scenarios hold both
sides of each rule (an edit that is refused on a feature branch and accepted on a
release branch), and a mutation pass breaks one rule in a copy of the script and
requires the scenario guarding it to fail. An undetected mutant fails this run.

Run:  python3 tools/test_change_notes.py [--no-mutants] [-k SUBSTRING]
Exit: 0 all passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared"
SRC = SHARED / "scripts/delivery"
PY = Path(sys.executable).as_posix()
FILES = ["delivery_common.py", "change_notes.py"]

_TMP = Path(tempfile.mkdtemp(prefix="change-notes-test-"))
_GITCONFIG = _TMP / "gitconfig"
_GITCONFIG.write_text(
    "[user]\n\tname = Notes Test\n\temail = notes@example.com\n"
    "[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n",
    encoding="utf-8",
)


def env() -> dict:
    e = os.environ.copy()
    for v in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX"):
        e.pop(v, None)
    e.update(GIT_CONFIG_GLOBAL=str(_GITCONFIG), GIT_CONFIG_NOSYSTEM="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return e


def rmtree(path: Path) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=onerror)


class R:
    def __init__(self, p: subprocess.CompletedProcess):
        self.code, self.out, self.err = p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")

    @property
    def text(self) -> str:
        return self.out + self.err


def run(cmd: list, cwd: Path) -> R:
    return R(subprocess.run([str(c) for c in cmd], cwd=cwd, env=env(), capture_output=True, check=False))


class T:
    def __init__(self, name: str, quiet: bool = False):
        self.name, self.quiet, self.total, self.failures = name, quiet, 0, []

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.total += 1
        if not ok:
            self.failures.append(label)
            if not self.quiet:
                print("    FAIL %s%s" % (label, ("\n      " + detail.strip().replace("\n", "\n      ")) if detail else ""))
        return ok


SPEC_A = """# Alpha spec

**Version:** 7.0.0

## 1. Rules

Text.

## What changed

**7.0.0 \u2014 2026-01-01.** First.

## Appendix

Tail.
"""
SPEC_B = """# Beta spec

**Version:** 1.4.2

## What changed since 1.0

**1.4.2 \u2014 2026-01-01.** Older.
"""


PLUGIN_JSON = """{
  "name": "p",
  "description": "A plugin.",
  "version": "2.3.4",
  "author": {
    "name": "X"
  }
}
"""
PLUGIN = "plugins/p/.claude-plugin/plugin.json"


class Box:
    """A repository on `main` with two specs; the scripts under test live in scripts/delivery."""

    def __init__(self, scripts: Path, gate: dict | None = None, config: dict | None = None):
        self.root = Path(tempfile.mkdtemp(dir=_TMP))
        self.scripts = scripts
        self.git("init", "-q")
        d = self.root / "scripts/delivery"
        d.mkdir(parents=True)
        for f in FILES:
            shutil.copy2(scripts / f, d / f)
        if config is None:
            cfg = {"schema": 1, "default_branch": "main", "packages": {"kind": "go-modules"},
                   "steps": [{"name": "x", "scope": "always", "run": "true"}]}
            cfg.update(gate or {})
            self.write("scripts/delivery/gate.json", json.dumps(cfg, indent=2))
        else:  # no gate.json at all: the settings live in --config
            self.write("tools/cfg.json", json.dumps(config, indent=2))
        self.write("plugins/p/.claude-plugin/plugin.json", PLUGIN_JSON)
        self.write("docs/specs/alpha.md", SPEC_A)
        self.write("docs/specs/beta.md", SPEC_B)
        self.write("CHANGELOG.md", "# Changelog\n")
        self.commit("base")

    def git(self, *a) -> R:
        r = run(["git", *a], self.root)
        if r.code != 0:
            raise RuntimeError("git %s: %s" % (" ".join(a), r.text))
        return r

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def commit(self, msg: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def branch(self, name: str) -> None:
        self.git("checkout", "-q", "-b", name)

    def note(self, name: str, spec: str, change: str, text: str, plugin: str = "") -> None:
        self.write("docs/specs/changes/%s.md" % name,
                   "---\n%s%schange: %s\n---\n%s\n" % (
                       "spec: %s       # the spec\n" % spec if spec else "",
                       "plugin: %s\n" % plugin if plugin else "", change, text))

    def check(self, *extra: str) -> R:
        return run([PY, "scripts/delivery/change_notes.py", "check", "--base-ref", "main", *extra], self.root)

    def fold(self, *extra: str) -> R:
        return run([PY, "scripts/delivery/change_notes.py", "fold", "--date", "2026-10-11", *extra], self.root)


def box(scripts: Path, gate: dict | None = None) -> Box:
    return Box(scripts, gate)


def box_cfg(scripts: Path, config: dict) -> Box:
    return Box(scripts, config=config)


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------

def sc_check_pass(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS1-feature")
    b.note("DS1-a", "docs/specs/alpha.md", "minor", "Added a thing.")
    b.write("docs/specs/alpha.md", SPEC_A.replace("Text.", "Text, edited."))  # body edits are fine
    b.commit("note")
    r = b.check()
    t.check("a note and a body edit pass", r.code == 0 and "ok" in r.out, r.text)
    b2 = box(s)
    b2.branch("DS1-nothing")
    r = b2.check()
    t.check("no change at all passes", r.code == 0, r.text)


def sc_check_version(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS2-version")
    b.write("docs/specs/alpha.md", SPEC_A.replace("7.0.0\n\n## 1", "7.1.0\n\n## 1"))
    b.commit("bump")
    r = b.check()
    t.check("a Version edit fails", r.code == 1, r.text)
    t.check("names the file and line", "docs/specs/alpha.md:3:" in r.out and "Version" in r.out, r.text)
    t.check("says to add a change note", "change note" in r.out, r.text)


def sc_check_changelog(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS3-log")
    b.write("docs/specs/alpha.md", SPEC_A.replace("**7.0.0 \u2014 2026-01-01.** First.", "**7.0.0 \u2014 2026-01-01.** First.\n\n**7.1.0 \u2014 2026-02-02.** More."))
    b.commit("log")
    r = b.check()
    t.check("a change-log insertion fails", r.code == 1 and "docs/specs/alpha.md:" in r.out and "change log" in r.out, r.text)
    b2 = box(s)
    b2.branch("DS3-del")
    b2.write("docs/specs/alpha.md", SPEC_A.replace("**7.0.0 \u2014 2026-01-01.** First.\n\n", ""))
    b2.commit("del")
    r = b2.check()
    t.check("a change-log deletion fails", r.code == 1, r.text)
    b3 = box(s)
    b3.branch("DS3-beta")  # heading "What changed since 1.0" starts with the default heading
    b3.write("docs/specs/beta.md", SPEC_B + "\n**1.5.0 \u2014 2026-02-02.** x.\n")
    b3.commit("beta")
    r = b3.check()
    t.check("a heading that starts with the configured text counts", r.code == 1 and "beta.md" in r.out, r.text)
    b4 = box(s)
    b4.branch("DS3-after")  # an edit under the next heading is not the change log
    b4.write("docs/specs/alpha.md", SPEC_A.replace("Tail.", "Tail, edited."))
    b4.commit("tail")
    r = b4.check()
    t.check("an edit after the change-log section passes", r.code == 0, r.text)


def sc_check_changelog_file(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS4-changelog")
    b.write("CHANGELOG.md", "# Changelog\n\n- thing\n")
    b.write("docs/CHANGELOG-extra.md", "x\n")
    b.commit("cl")
    r = b.check()
    t.check("a CHANGELOG edit fails", r.code == 1 and "CHANGELOG.md" in r.out, r.text)
    t.check("any CHANGELOG* file is named", "CHANGELOG-extra.md" in r.out, r.text)


def sc_release(t: T, s: Path) -> None:
    for name in ("DS5-integration", "release/7.1"):
        b = box(s)
        b.branch(name)
        b.write("docs/specs/alpha.md", SPEC_A.replace("7.0.0\n\n## 1", "7.1.0\n\n## 1"))
        b.write("CHANGELOG.md", "# Changelog\n\n- x\n")
        b.commit("release edits")
        r = b.check()
        t.check("%s accepts Version and CHANGELOG edits" % name, r.code == 0 and "release branch" in r.out, r.text)
    b = box(s, {"release_branches": ["train-*", "hotfix/**"]})
    b.branch("train-7")
    b.write("CHANGELOG.md", "# Changelog\n\n- x\n")
    b.commit("cl")
    t.check("a custom release glob accepts", b.check().code == 0)
    b.git("checkout", "-q", "-b", "DS5-integration", "main")
    b.write("CHANGELOG.md", "# Changelog\n\n- y\n")
    b.commit("cl")
    t.check("the default glob is replaced by a custom one", b.check().code == 1)
    b.git("checkout", "-q", "-b", "hotfix/a/b", "main")
    b.write("CHANGELOG.md", "# Changelog\n\n- z\n")
    b.commit("cl")
    t.check("a ** glob matches nested names", b.check().code == 0)
    b.git("checkout", "-q", "--detach", "train-7")
    b.git("branch", "-f", "train-pointing", "HEAD")
    t.check("a detached HEAD uses the branches that point at it", b.check().code == 0)
    t.check("--branch overrides", b.check("--branch", "DS5-plain").code == 1)


def sc_custom_specs(t: T, s: Path) -> None:
    b = box(s, {"specs": ["docs/specs/alpha.md"], "changelog_heading": "Revision history"})
    b.branch("DS6-custom")
    b.write("docs/specs/beta.md", SPEC_B.replace("1.4.2\n", "1.5.0\n", 1))  # not a listed spec
    b.commit("beta")
    t.check("an unlisted file is not a spec", b.check().code == 0)
    b.write("docs/specs/alpha.md", SPEC_A.replace("## What changed", "## Revision history").replace("Tail.", "Tail."))
    b.commit("heading renamed")
    r = b.check()
    t.check("a rename of the configured heading is a change-log edit", r.code == 1, r.text)
    c = box(s)
    c.branch("DS6-new")
    c.write("docs/specs/new.md", "# New\n\n**Version:** 1.0.0\n\n## What changed\n\nx\n")
    c.commit("new spec")
    t.check("a new spec file may carry its first version", c.check().code == 0)


def sc_not_ancestor(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS7-feature")
    b.note("DS7-a", "docs/specs/alpha.md", "patch", "x.")
    b.commit("note")
    b.git("checkout", "-q", "main")
    b.write("docs/specs/alpha.md", SPEC_A.replace("7.0.0\n\n## 1", "7.0.1\n\n## 1"))  # main moves on, bumping the version
    b.commit("main bump")
    b.git("checkout", "-q", "DS7-feature")
    r = b.check()
    t.check("works when the base is not an ancestor (merge base used)", r.code == 0, r.text)
    r = run([PY, "scripts/delivery/change_notes.py", "check", "--base-ref", "nope"], b.root)
    t.check("an unknown base is a usage error", r.code == 2, r.text)


def sc_bad_notes(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS8-bad")
    b.write("docs/specs/changes/DS8-a.md", "---\nspec: docs/specs/alpha.md\nchange: huge\n---\nx\n")
    b.commit("bad")
    r = b.check()
    t.check("a bad change kind fails and names the note", r.code == 1 and "DS8-a.md" in r.out and "huge" in r.out, r.text)
    r = b.fold()
    t.check("fold refuses a malformed note", r.code == 1 and "DS8-a.md" in r.out, r.text)
    t.check("and writes nothing", b.read("docs/specs/alpha.md") == SPEC_A)


def folded(b: Box) -> None:
    b.commit("notes")


def sc_fold_kinds(t: T, s: Path) -> None:
    for kind, want in (("patch", "7.0.1"), ("minor", "7.1.0"), ("major", "8.0.0")):
        b = box(s)
        b.branch("DS9-integration")
        b.note("DS9-a", "docs/specs/alpha.md", kind, "Did the %s thing." % kind)
        folded(b)
        r = b.fold()
        text = b.read("docs/specs/alpha.md")
        t.check("%s bumps to %s" % (kind, want), r.code == 0 and "**Version:** %s\n" % want in text, r.text + text)
        t.check("%s writes the entry under the heading" % kind,
                "## What changed\n\n**%s \u2014 2026-10-11.**\n\n- Did the %s thing.\n\n**7.0.0" % (want, kind) in text, text)
        t.check("%s removes the note" % kind, not (b.root / "docs/specs/changes/DS9-a.md").exists())
        t.check("%s leaves the rest alone" % kind, "## Appendix\n\nTail.\n" in text and "## 1. Rules" in text)
        t.check("%s release branch check passes after fold" % kind, b.check().code == 0)


def sc_fold_resets(t: T, s: Path) -> None:
    for kind, want in (("patch", "1.4.3"), ("minor", "1.5.0"), ("major", "2.0.0")):
        b = box(s)
        b.branch("DS9b-integration")
        b.note("DS9b-a", "docs/specs/beta.md", kind, "x.")
        folded(b)
        b.fold()
        t.check("1.4.2 + %s = %s (lower parts reset)" % (kind, want), "**Version:** %s\n" % want in b.read("docs/specs/beta.md"))


def sc_fold_several(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS10-integration")
    b.note("DS10-a", "docs/specs/alpha.md", "patch", "First.")
    b.note("DS10-b", "docs/specs/alpha.md", "major", "Second,\nover two lines.")
    b.note("DS10-c", "docs/specs/alpha.md", "minor", "Third.")
    b.note("DS10-d", "docs/specs/beta.md", "minor", "Beta thing.")
    folded(b)
    r = b.fold()
    a, bt = b.read("docs/specs/alpha.md"), b.read("docs/specs/beta.md")
    t.check("several notes bump once, by the highest kind", "**Version:** 8.0.0\n" in a, a)
    t.check("one entry, one bullet per note, in file order",
            "**8.0.0 \u2014 2026-10-11.**\n\n- First.\n- Second, over two lines.\n- Third.\n\n**7.0.0" in a, a)
    t.check("a second spec is bumped on its own", "**Version:** 1.5.0\n" in bt and "**1.5.0 \u2014 2026-10-11.**\n\n- Beta thing.\n" in bt, bt)
    t.check("the heading text may continue (What changed since 1.0)", "## What changed since 1.0\n\n**1.5.0" in bt, bt)
    t.check("the summary names both specs", "alpha.md" in r.out and "beta.md" in r.out and "7.0.0 -> 8.0.0" in r.out, r.text)
    t.check("all notes are deleted", not list((b.root / "docs/specs/changes").glob("*.md")))
    r2 = b.fold()
    t.check("fold again is a no-op", r2.code == 0 and "nothing to fold" in r2.out and b.read("docs/specs/alpha.md") == a, r2.text)


def sc_fold_dry(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS11-integration")
    b.note("DS11-a", "docs/specs/alpha.md", "minor", "Planned.")
    folded(b)
    r = b.fold("--dry-run")
    t.check("dry run reports the plan", r.code == 0 and "would fold" in r.out and "7.0.0 -> 7.1.0" in r.out and "Planned." in r.out, r.text)
    t.check("dry run writes nothing", b.read("docs/specs/alpha.md") == SPEC_A and (b.root / "docs/specs/changes/DS11-a.md").exists())
    t.check("dry run leaves the tree clean", b.git("status", "--porcelain").out.strip() == "")


def sc_fold_errors(t: T, s: Path) -> None:
    b = box(s)
    b.branch("DS12-integration")
    b.note("DS12-a", "docs/specs/missing.md", "minor", "x.")
    r = b.fold()
    t.check("a note for a missing spec fails (exit 2)", r.code == 2 and "missing.md" in r.text, r.text)
    (b.root / "docs/specs/changes/DS12-a.md").unlink()
    b.write("docs/specs/gamma.md", "# G\n\n## What changed\n")
    b.note("DS12-b", "docs/specs/gamma.md", "minor", "x.")
    r = b.fold()
    t.check("a spec with no Version line fails (exit 2)", r.code == 2 and "Version" in r.text, r.text)
    (b.root / "docs/specs/changes/DS12-b.md").unlink()
    b.write("docs/specs/delta.md", "# D\n\n**Version:** 1.0.0\n")
    b.note("DS12-c", "docs/specs/delta.md", "minor", "x.")
    r = b.fold()
    t.check("a spec with no change-log heading fails (exit 2)", r.code == 2 and "change-log heading" in r.text, r.text)
    t.check("a failed fold deleted no note", (b.root / "docs/specs/changes/DS12-c.md").exists())
    c = box(s)
    c.branch("DS12-crlf")
    c.write("docs/specs/alpha.md", SPEC_A.replace("\n", "\r\n"))
    c.note("DS12-d", "docs/specs/alpha.md", "patch", "x.")
    c.git("add", "-A")
    c.git("commit", "-q", "-m", "crlf")
    c.fold()
    raw = (c.root / "docs/specs/alpha.md").read_bytes().decode("utf-8")
    t.check("CRLF specs stay CRLF", "\r\n" in raw and "\n" not in raw.replace("\r\n", ""), repr(raw[:200]))


def sc_gate_json(t: T, s: Path) -> None:
    cases = [
        ({"specs": "docs/specs/*.md"}, "'specs' must be a list of strings"),
        ({"specs": [1]}, "'specs' must be a list of strings"),
        ({"release_branches": "main"}, "'release_branches' must be a list of strings"),
        ({"changelog_heading": ""}, "'changelog_heading' must be a non-empty string"),
        ({"changelog_heading": 3}, "'changelog_heading' must be a non-empty string"),
    ]
    for gate, msg in cases:
        b = box(s, gate)
        b.branch("DS13-x")
        for cmd in ("check", "fold"):
            r = run([PY, "scripts/delivery/change_notes.py", cmd, *(["--base-ref", "main"] if cmd == "check" else [])], b.root)
            t.check("%s %s -> %s" % (cmd, json.dumps(gate), msg), r.code == 2 and msg in r.text, r.text)
    b = box(s, {"specs": [], "release_branches": [], "changelog_heading": "Log"})
    r = run([PY, "scripts/delivery/change_notes.py", "fold"], b.root)
    t.check("valid values are accepted", r.code == 0, r.text)


CFG = {"specs": ["docs/specs/*.md"], "plugins": ["plugins/*/.claude-plugin/plugin.json"],
       "release_branches": ["*-integration"], "default_branch": "main"}


def cfg_run(b: Box, cmd: str, *extra: str) -> R:
    base = ["--base-ref", "main"] if cmd == "check" else ["--date", "2026-10-11"]
    return run([PY, "scripts/delivery/change_notes.py", cmd, "--config", "tools/cfg.json", *base, *extra], b.root)


def sc_config(t: T, s: Path) -> None:
    b = box_cfg(s, CFG)
    b.branch("DS14-feature")
    b.note("DS14-a", "docs/specs/alpha.md", "minor", "Added.")
    b.write("docs/specs/alpha.md", SPEC_A.replace("Text.", "Text, edited."))
    b.commit("note")
    r = cfg_run(b, "check")
    t.check("--config needs no gate.json; a note passes", r.code == 0 and "ok" in r.out, r.text)
    b.write("docs/specs/alpha.md", SPEC_A.replace("7.0.0\n\n## 1", "7.1.0\n\n## 1"))
    b.commit("bump")
    r = cfg_run(b, "check")
    t.check("--config: a Version edit fails", r.code == 1 and "alpha.md:3:" in r.out, r.text)
    r = run([PY, "scripts/delivery/change_notes.py", "check", "--base-ref", "main"], b.root)
    t.check("without --config the missing gate.json is a usage error", r.code == 2 and "gate.json" in r.text, r.text)
    b.git("checkout", "-q", "-b", "DS14-integration", "main")
    b.write("docs/specs/alpha.md", SPEC_A.replace("7.0.0\n\n## 1", "7.1.0\n\n## 1"))
    b.commit("release bump")
    t.check("--config: release_branches is honoured", cfg_run(b, "check").code == 0)
    b.git("checkout", "-q", "-b", "release/9", "main")
    b.write("CHANGELOG.md", "# Changelog\n\n- x\n")
    b.commit("cl")
    t.check("--config: the default release globs are replaced", cfg_run(b, "check").code == 1)
    c = box_cfg(s, CFG)
    c.branch("DS14-integration")
    c.note("DS14-b", "docs/specs/alpha.md", "patch", "Fixed.")
    c.commit("note")
    r = cfg_run(c, "fold")
    t.check("--config: fold bumps", r.code == 0 and "**Version:** 7.0.1\n" in c.read("docs/specs/alpha.md"), r.text)
    d = box_cfg(s, {"specs": "x"})
    r = cfg_run(d, "fold")
    t.check("--config: a bad value is named with the config path", r.code == 2 and "tools/cfg.json: 'specs' must be a list" in r.text, r.text)
    d = box_cfg(s, {"changelog_headings": {"docs/specs/alpha.md": 3}})
    r = cfg_run(d, "fold")
    t.check("--config: changelog_headings must map to strings", r.code == 2 and "changelog_headings" in r.text, r.text)
    d = box_cfg(s, {"default_branch": ""})
    r = cfg_run(d, "fold")
    t.check("--config: default_branch must be non-empty", r.code == 2 and "default_branch" in r.text, r.text)
    d = box_cfg(s, CFG)
    r = run([PY, "scripts/delivery/change_notes.py", "fold", "--config", "tools/nope.json"], d.root)
    t.check("--config: a missing file is a usage error", r.code == 2 and "nope.json not found" in r.text, r.text)
    d.write("tools/bad.json", "{")
    r = run([PY, "scripts/delivery/change_notes.py", "fold", "--config", "tools/bad.json"], d.root)
    t.check("--config: invalid JSON is a usage error", r.code == 2 and "not valid JSON" in r.text, r.text)


def sc_headings(t: T, s: Path) -> None:
    cfg = dict(CFG, changelog_heading="What changed", changelog_headings={"docs/specs/beta.md": "History", "docs/specs/alpha.md": ""})
    beta = SPEC_B.replace("What changed since 1.0", "History of beta")
    b = box_cfg(s, cfg)
    b.write("docs/specs/beta.md", beta)
    b.commit("beta heading")
    b.branch("DS15-feature")
    b.write("docs/specs/beta.md", beta + "\n**1.5.0 \u2014 2026-02-02.** x.\n")
    b.commit("beta log")
    r = cfg_run(b, "check")
    t.check("a per-spec heading marks that spec's change log", r.code == 1 and "beta.md" in r.out and "History" in r.out, r.text)
    b.git("checkout", "-q", "main")
    b.git("checkout", "-q", "-b", "DS15-other")
    b.write("docs/specs/alpha.md", SPEC_A.replace("**7.0.0 \u2014 2026-01-01.** First.", "**7.0.0 \u2014 2026-01-01.** First, edited."))
    b.commit("alpha log")
    t.check("a spec with heading \"\" has no change log to guard", cfg_run(b, "check").code == 0)
    b.write("docs/specs/alpha.md", SPEC_A.replace("7.0.0\n\n## 1", "7.0.1\n\n## 1"))
    b.commit("alpha version")
    t.check("but its Version is still guarded", cfg_run(b, "check").code == 1)
    c = box_cfg(s, cfg)
    c.write("docs/specs/beta.md", beta)
    c.commit("beta heading")
    c.branch("DS15-integration")
    c.note("DS15-a", "docs/specs/alpha.md", "minor", "Alpha thing.")
    c.note("DS15-b", "docs/specs/beta.md", "patch", "Beta thing.")
    c.commit("notes")
    r = cfg_run(c, "fold")
    a, bt = c.read("docs/specs/alpha.md"), c.read("docs/specs/beta.md")
    t.check("fold uses each spec's own heading", r.code == 0 and "## History of beta\n\n**1.4.3 \u2014 2026-10-11.**\n\n- Beta thing." in bt, r.text + bt)
    t.check("a spec with no change log is only bumped", a == SPEC_A.replace("7.0.0\n\n## 1", "7.1.0\n\n## 1"), a)


def sc_plugins(t: T, s: Path) -> None:
    b = box_cfg(s, CFG)
    b.branch("DS16-feature")
    b.write(PLUGIN, PLUGIN_JSON.replace("A plugin.", "Another plugin."))
    b.commit("description")
    t.check("a plugin.json edit other than version passes", cfg_run(b, "check").code == 0)
    b.write(PLUGIN, PLUGIN_JSON.replace("2.3.4", "2.4.0"))
    b.commit("version")
    r = cfg_run(b, "check")
    t.check("a plugin version edit fails and names file:line", r.code == 1 and "%s:4:" % PLUGIN in r.out and "version" in r.out, r.text)
    t.check("and points at a change note", "change note" in r.out, r.text)
    b.git("checkout", "-q", "-b", "DS16-integration")
    t.check("a release branch accepts a plugin version edit", cfg_run(b, "check").code == 0)
    n = box_cfg(s, dict(CFG, plugins=[]))
    n.branch("DS16-unlisted")
    n.write(PLUGIN, PLUGIN_JSON.replace("2.3.4", "2.4.0"))
    n.commit("version")
    t.check("a plugin not in 'plugins' is not guarded", cfg_run(n, "check").code == 0)
    for kind, want in (("patch", "2.3.5"), ("minor", "2.4.0"), ("major", "3.0.0")):
        f = box_cfg(s, CFG)
        f.branch("DS16b-integration")
        f.note("DS16b-a", "", kind, "Plugin %s." % kind, plugin=PLUGIN)
        f.commit("note")
        r = cfg_run(f, "fold")
        text = f.read(PLUGIN)
        t.check("%s bumps the plugin to %s, rest untouched" % (kind, want), r.code == 0 and text == PLUGIN_JSON.replace("2.3.4", want), r.text + text)
        t.check("%s removes the note" % kind, not (f.root / "docs/specs/changes/DS16b-a.md").exists())
    g = box_cfg(s, CFG)
    g.branch("DS16c-integration")
    g.note("DS16c-a", "docs/specs/alpha.md", "patch", "Both.", plugin=PLUGIN)
    g.note("DS16c-b", "", "minor", "Plugin only.", plugin=PLUGIN)
    g.commit("notes")
    r = cfg_run(g, "fold", "--dry-run")
    t.check("dry run reports spec and plugin", r.code == 0 and "2.3.4 -> 2.4.0" in r.out and "7.0.0 -> 7.0.1" in r.out, r.text)
    t.check("dry run writes nothing", g.read(PLUGIN) == PLUGIN_JSON)
    r = cfg_run(g, "fold")
    t.check("a note may name both; the plugin takes the highest kind of its notes",
            r.code == 0 and '"version": "2.4.0"' in g.read(PLUGIN) and "**Version:** 7.0.1\n" in g.read("docs/specs/alpha.md"), r.text)
    h = box_cfg(s, CFG)
    h.branch("DS16d-integration")
    h.note("DS16d-a", "", "minor", "x.", plugin="plugins/none/.claude-plugin/plugin.json")
    r = cfg_run(h, "fold")
    t.check("a note for a missing plugin fails (exit 2)", r.code == 2 and "none" in r.text, r.text)
    h = box_cfg(s, CFG)
    h.write("plugins/q.json", "{}\n")
    h.note("DS16e-a", "", "minor", "x.", plugin="plugins/q.json")
    r = cfg_run(h, "fold")
    t.check("a plugin without a version line fails (exit 2)", r.code == 2 and "version" in r.text, r.text)
    h.write("docs/specs/changes/DS16e-b.md", "---\nchange: minor\n---\nx\n")
    r = cfg_run(h, "check")
    t.check("a note naming neither spec nor plugin is malformed", r.code == 1 and "DS16e-b.md" in r.out, r.text)


def sc_track_gates(t: T, s: Path) -> None:
    for track in ("ts", "go", "rust", "dotnet"):
        cfg = json.loads((SHARED.parent / track / "scripts/delivery/gate.json").read_text(encoding="utf-8"))
        steps = [x for x in cfg["steps"] if x["name"] == "change-notes"]
        ok = (len(steps) == 1 and steps[0]["scope"] == "always" and steps[0]["pre_push"] is True
              and "change_notes.py check --base-ref {base}" in steps[0]["run"])
        t.check("%s gate.json has the change-notes step" % track, ok, json.dumps(steps))


def staged(b: Box, *extra: str) -> R:
    return run([PY, "scripts/delivery/change_notes.py", "check", "--staged", *extra], b.root)


BUMPED = SPEC_A.replace("7.0.0\n\n## 1", "7.1.0\n\n## 1")


def sc_staged(t: T, s: Path) -> None:
    b = box(s)
    b.branch("TC10-feature")
    b.write("docs/specs/alpha.md", SPEC_A.replace("Text.", "Text, edited."))
    b.git("add", "-A")
    r = staged(b)
    t.check("staged: a body edit passes", r.code == 0 and "ok" in r.out, r.text)
    b.write("docs/specs/alpha.md", BUMPED)
    b.git("add", "-A")
    r = staged(b)
    t.check("staged: a staged Version edit fails", r.code == 1 and "docs/specs/alpha.md:3:" in r.out, r.text)
    t.check("staged: says to add a change note", "change note" in r.out, r.text)
    b.git("reset", "-q")  # the edit stays in the working tree, unstaged
    r = staged(b)
    t.check("staged: an unstaged Version edit is not judged", r.code == 0, r.text)
    b.git("checkout", "--", "docs/specs/alpha.md")
    b.write("CHANGELOG.md", "# Changelog\n\n- x\n")
    b.git("add", "-A")
    r = staged(b)
    t.check("staged: a CHANGELOG edit fails", r.code == 1 and "CHANGELOG.md" in r.out, r.text)
    p = box_cfg(s, CFG)
    p.branch("TC10-plugin")
    p.write(PLUGIN, PLUGIN_JSON.replace("A plugin.", "Another plugin."))
    p.git("add", "-A")
    cmd = [PY, "scripts/delivery/change_notes.py", "check", "--staged", "--config", "tools/cfg.json"]
    t.check("staged: a plugin.json edit other than version passes", run(cmd, p.root).code == 0)
    p.write(PLUGIN, PLUGIN_JSON.replace("2.3.4", "2.4.0"))
    p.git("add", "-A")
    r = run(cmd, p.root)
    t.check("staged: a plugin version edit fails", r.code == 1 and "plugin.json:4:" in r.out, r.text)
    r = staged(b, "--branch", "TC10-integration")
    t.check("staged: a release branch is exempt", r.code == 0 and "release branch" in r.out, r.text)
    c = box(s)
    c.git("checkout", "-q", "-b", "TC10-other")
    c.write("docs/specs/alpha.md", BUMPED)
    c.git("add", "-A")
    r = run([PY, "scripts/delivery/change_notes.py", "check", "--staged", "--base-ref", "nope"], c.root)
    t.check("staged: needs no base ref", r.code == 1 and "nope" not in r.text, r.text)


def sc_staged_hook(t: T, s: Path) -> None:
    bash = shutil.which("bash")
    if not bash:
        t.check("pre-commit hook: bash is available (skipped)", True)
        return
    hook = SHARED / ".githooks/pre-commit"
    shim = _TMP / "shim"
    shim.mkdir(exist_ok=True)
    (shim / "python3").write_text('#!/bin/sh\nexec "%s" "$@"\n' % PY, encoding="utf-8", newline="\n")
    (shim / "python3").chmod(0o755)

    def hook_run(b: Box) -> R:
        e = env()
        e["PATH"] = shim.as_posix() + os.pathsep + e["PATH"]
        return R(subprocess.run([bash, ".githooks/pre-commit"], cwd=b.root, env=e, capture_output=True, check=False))

    b = box(s)
    b.write(".githooks/pre-commit", hook.read_text(encoding="utf-8"))
    b.commit("hook")
    b.branch("TC10-feature")
    b.write("docs/specs/alpha.md", BUMPED)
    b.git("add", "-A")
    r = hook_run(b)
    t.check("hook: refuses a staged Version edit off a release branch",
            r.code == 1 and "alpha.md:3:" in r.text and "change-note check" in r.text, r.text)
    b.git("reset", "-q")
    b.write("docs/specs/alpha.md", SPEC_A.replace("Text.", "Text, edited."))
    b.git("add", "-A")
    r = hook_run(b)
    t.check("hook: lets a body edit through", r.code == 0, r.text)
    c = box(s)
    c.write(".githooks/pre-commit", hook.read_text(encoding="utf-8"))
    c.commit("hook")
    c.git("checkout", "-q", "-b", "TC10-integration")
    c.write("docs/specs/alpha.md", BUMPED)
    c.git("add", "-A")
    t.check("hook: a release branch may edit the version", hook_run(c).code == 0)
    d = box(s)
    d.write(".githooks/pre-commit", hook.read_text(encoding="utf-8"))
    d.git("rm", "-q", "--cached", "scripts/delivery/gate.json")
    (d.root / "scripts/delivery/gate.json").unlink()
    d.commit("hook, no settings")
    d.git("checkout", "-q", "-b", "TC10-feature")
    d.write("docs/specs/alpha.md", BUMPED)
    d.git("add", "-A")
    t.check("hook: does nothing without change-note settings", hook_run(d).code == 0)
    import time
    t0 = time.time()
    hook_run(b)
    t.check("hook: runs in under 2 s", time.time() - t0 < 2.0, "%.2f s" % (time.time() - t0))


SCENARIOS = [
    ("check-pass", sc_check_pass, "check passes with only a note"),
    ("staged", sc_staged, "check --staged"),
    ("staged-hook", sc_staged_hook, "the pre-commit hook runs the staged check"),
    ("check-version", sc_check_version, "version edit"),
    ("check-changelog", sc_check_changelog, "change-log edit"),
    ("check-changelog-file", sc_check_changelog_file, "CHANGELOG edit"),
    ("release", sc_release, "release branches"),
    ("custom-specs", sc_custom_specs, "custom specs and heading"),
    ("not-ancestor", sc_not_ancestor, "merge base"),
    ("bad-notes", sc_bad_notes, "malformed notes"),
    ("fold-kinds", sc_fold_kinds, "fold bumps"),
    ("fold-resets", sc_fold_resets, "lower parts reset"),
    ("fold-several", sc_fold_several, "several notes, two specs, idempotent"),
    ("fold-dry", sc_fold_dry, "dry run"),
    ("fold-errors", sc_fold_errors, "fold errors, CRLF"),
    ("gate-json", sc_gate_json, "gate.json validation"),
    ("config", sc_config, "--config instead of gate.json"),
    ("headings", sc_headings, "per-spec change-log headings"),
    ("plugins", sc_plugins, "plugin versions"),
    ("track-gates", sc_track_gates, "track gate.json steps"),
]

# (script, old text, new text, scenarios that must notice). Each breaks one rule.
MUTANTS = [
    ("change_notes.py", "if not release:\n        base_ref", "if True:\n        base_ref", ["release"]),
    ("change_notes.py", "if VERSION_RE.match(text) or text.startswith(\"**Version:**\"):", "if False:", ["check-version"]),
    ("change_notes.py", "elif rng and rng[0] <= no <= rng[1]:", "elif False:", ["check-changelog"]),
    ("change_notes.py", "if re.match(r\"(?i)^changelog\"", "if re.match(r\"^NEVER\"", ["check-changelog-file"]),
    ("change_notes.py", "def is_spec(path: str, cfg: dict) -> bool:\n    if path.startswith(NOTES_DIR + \"/\"):\n        return False\n",
     "def is_spec(path: str, cfg: dict) -> bool:\n    return True\n", ["custom-specs"]),
    ("change_notes.py", "if old_lines is None or new_lines is None:", "if False:", ["custom-specs"]),
    ("change_notes.py", "key=KINDS.index)", "key=lambda k: -KINDS.index(k))", ["fold-kinds", "fold-several"]),
    ("change_notes.py", "return major, minor + 1, 0", "return major, minor + 1, patch", ["fold-resets"]),
    ("change_notes.py", "return major + 1, 0, 0", "return major + 1, minor, patch", ["fold-resets"]),
    ("change_notes.py", "        for n in notes:\n            (root / n.path).unlink()\n", "", ["fold-kinds", "fold-several"]),
    ("change_notes.py", "if not args.dry_run:\n            with open", "if True:\n            with open", ["fold-dry"]),
    ("change_notes.py", "    at = rng[0]  # right under", "    at = len(lines)  # right under", ["fold-kinds"]),
    ("change_notes.py", "for spec, group in sorted(by_spec.items())", "for spec, group in sorted(by_spec.items())[:1]", ["fold-several"]),
    ("change_notes.py", "eol = \"\\r\\n\" if \"\\r\\n\" in text else \"\\n\"", "eol = \"\\n\"", ["fold-errors"]),
    ("change_notes.py", "if kind not in KINDS:", "if False:", ["bad-notes"]),
    ("change_notes.py", "if not notes:\n        print", "if False:\n        print", ["fold-several"]),
    ("change_notes.py", "if config:\n        path = root / config", "if False:\n        path = root / config", ["config"]),
    ("change_notes.py", "return cfg[\"changelog_headings\"].get(spec, cfg[\"changelog_heading\"])", "return cfg[\"changelog_heading\"]", ["headings"]),
    ("change_notes.py", "if heading:  # a spec", "if True:  # a spec", ["headings"]),
    ("change_notes.py", "if is_plugin(path, cfg):", "if False:", ["plugins", "staged"]),
    ("change_notes.py", "if n.plugin:\n            by_plugin", "if False:\n            by_plugin", ["plugins"]),
    ("change_notes.py", "if not spec and not plugin:", "if False:", ["plugins"]),
    ("delivery_common.py", "or not cfg[\"changelog_heading\"].strip():", "or False:", ["gate-json"]),
    ("delivery_common.py", "    for key in (\"specs\", \"release_branches\"):\n        cfg[key] = _str_list(cfg, key, where)\n", "", ["gate-json"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mutants", action="store_true")
    ap.add_argument("-k", default="")
    args = ap.parse_args()
    chosen = [sc for sc in SCENARIOS if args.k in sc[0]]
    bad = 0
    total = 0

    def run_scenarios(scripts: Path, names: list[str] | None, quiet: bool) -> list[T]:
        out = []
        for name, fn, _doc in chosen:
            if names is not None and name not in names:
                continue
            t = T(name, quiet)
            try:
                fn(t, scripts)
            except Exception:  # a crash is a failure
                t.failures.append("crashed")
                if not quiet:
                    traceback.print_exc()
            out.append(t)
        return out

    for t in run_scenarios(SRC, None, False):
        total += t.total
        status = "ok  " if not t.failures else "FAIL"
        print("%s %s (%d checks)" % (status, t.name, t.total))
        bad += bool(t.failures)

    if not args.no_mutants and not args.k:
        for i, (fname, old, new, guards) in enumerate(MUTANTS, 1):
            copy = _TMP / ("mut%d" % i)
            shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns("__pycache__"))
            text = (copy / fname).read_text(encoding="utf-8")
            if old not in text:
                print("FAIL mutant %d: text not found in %s: %r" % (i, fname, old[:60]))
                bad += 1
                continue
            (copy / fname).write_text(text.replace(old, new, 1), encoding="utf-8", newline="")
            res = run_scenarios(copy, guards, True)
            caught = any(t.failures for t in res)
            print("%s mutant %d (%s) %s" % ("ok  " if caught else "FAIL", i, ", ".join(guards), "caught" if caught else "NOT DETECTED"))
            bad += not caught
    rmtree(_TMP)
    print("\n%s: %d checks in %d scenarios" % ("PASSED" if not bad else "FAILED (%d)" % bad, total, len(chosen)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
