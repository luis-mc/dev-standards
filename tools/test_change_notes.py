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


class Box:
    """A repository on `main` with two specs; the scripts under test live in scripts/delivery."""

    def __init__(self, scripts: Path, gate: dict | None = None):
        self.root = Path(tempfile.mkdtemp(dir=_TMP))
        self.scripts = scripts
        self.git("init", "-q")
        d = self.root / "scripts/delivery"
        d.mkdir(parents=True)
        for f in FILES:
            shutil.copy2(scripts / f, d / f)
        cfg = {"schema": 1, "default_branch": "main", "packages": {"kind": "go-modules"},
               "steps": [{"name": "x", "scope": "always", "run": "true"}]}
        cfg.update(gate or {})
        self.write("scripts/delivery/gate.json", json.dumps(cfg, indent=2))
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

    def note(self, name: str, spec: str, change: str, text: str) -> None:
        self.write("docs/specs/changes/%s.md" % name,
                   "---\nspec: %s       # the spec\nchange: %s\n---\n%s\n" % (spec, change, text))

    def check(self, *extra: str) -> R:
        return run([PY, "scripts/delivery/change_notes.py", "check", "--base-ref", "main", *extra], self.root)

    def fold(self, *extra: str) -> R:
        return run([PY, "scripts/delivery/change_notes.py", "fold", "--date", "2026-10-11", *extra], self.root)


def box(scripts: Path, gate: dict | None = None) -> Box:
    return Box(scripts, gate)


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


def sc_track_gates(t: T, s: Path) -> None:
    for track in ("ts", "go", "rust", "dotnet"):
        cfg = json.loads((SHARED.parent / track / "scripts/delivery/gate.json").read_text(encoding="utf-8"))
        steps = [x for x in cfg["steps"] if x["name"] == "change-notes"]
        ok = (len(steps) == 1 and steps[0]["scope"] == "always" and steps[0]["pre_push"] is True
              and "change_notes.py check --base-ref {base}" in steps[0]["run"])
        t.check("%s gate.json has the change-notes step" % track, ok, json.dumps(steps))


SCENARIOS = [
    ("check-pass", sc_check_pass, "check passes with only a note"),
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
