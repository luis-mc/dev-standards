#!/usr/bin/env python3
"""Change notes: how a spec's version and change log are kept by one hand (CONTRACT.md U7).

    change_notes.py check [--base-ref REF] [--branch NAME]
    change_notes.py fold  [--dry-run] [--date YYYY-MM-DD]

A change note is docs/specs/changes/<task-id>-<slug>.md:

    ---
    spec: docs/specs/stack-profile.md
    change: minor            # patch | minor | major
    ---
    One or two sentences for the change log.

check (a gate.json step, scope "always", pre_push): on a branch that is not a
release branch, fails when the diff against the base (the merge base with REF)
changes a spec's **Version:** line or its change-log section, or any CHANGELOG*
file; each offence is named as file:line with the fix (add a change note
instead). It also fails on a malformed note. On a release branch only the notes
are checked.

fold (run on a release branch before the ready PR): for each spec with notes,
bumps its **Version:** by the highest change kind, writes one change-log entry
under the change-log heading (new version, date, one bullet per note) and
deletes the folded notes. No notes: nothing to do. --dry-run prints the same
summary and writes nothing.

gate.json keys (all optional): "specs" (globs; default docs/specs/*.md),
"changelog_heading" (a heading starting with this text; default "What changed"),
"release_branches" (globs; default *-integration and release/*).

Python 3.11+, standard library only. Exit: 0 ok, 1 offences found, 2 usage or
configuration error.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep scripts/delivery/ free of __pycache__ (a clean tree is required)

import delivery_common as dc

NOTES_DIR = "docs/specs/changes"
KINDS = ("patch", "minor", "major")
VERSION_RE = re.compile(r"^(\*\*Version:\*\*\s*)(\d+)\.(\d+)\.(\d+)(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


# --------------------------------------------------------------------------
# paths and globs
# --------------------------------------------------------------------------

def glob_to_re(pattern: str) -> re.Pattern:
    """A path glob: * and ? stay inside one directory, ** crosses them."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if c == "*":
            out.append(".*" if pattern.startswith("**", i) else "[^/]*")
            i += 2 if pattern.startswith("**", i) else 1
            continue
        out.append("[^/]" if c == "?" else re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def is_spec(path: str, cfg: dict) -> bool:
    if path.startswith(NOTES_DIR + "/"):
        return False
    return any(glob_to_re(g).match(path) for g in cfg["specs"])


def is_release_branch(names: list[str], cfg: dict) -> bool:
    return any(fnmatch.fnmatchcase(n, g) for n in names for g in cfg["release_branches"])


def branch_names(root: Path, forced: str | None) -> list[str]:
    """The branch the check runs for. Detached (fast_guards checks a pushed commit
    in a detached worktree): the local branches that point at HEAD."""
    if forced:
        return [forced]
    name = dc.current_branch(root)
    if name:
        return [name]
    out = dc.git(["for-each-ref", "--points-at", "HEAD", "--format=%(refname:short)", "refs/heads"],
                 cwd=root, check=False)
    return out.split()


# --------------------------------------------------------------------------
# spec text
# --------------------------------------------------------------------------

def changelog_range(lines: list[str], heading: str) -> tuple[int, int] | None:
    """1-based inclusive line range of the change-log section: its heading up to
    the line before the next heading of the same or a higher level."""
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not (m and m.group(2).startswith(heading)):
            continue
        level = len(m.group(1))
        end = len(lines)
        for j in range(i + 1, len(lines)):
            n = HEADING_RE.match(lines[j])
            if n and len(n.group(1)) <= level:
                end = j
                break
        return i + 1, end
    return None


def show(root: Path, ref: str, path: str) -> list[str] | None:
    p = dc.run_git(["show", "%s:%s" % (ref, path)], cwd=root, check=False)
    return p.stdout.splitlines() if p.returncode == 0 else None


def changed_lines(root: Path, base: str, path: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(removed, added) lines of one file between base and HEAD: (line number, text)."""
    diff = dc.run_git(["diff", "-U0", "--no-renames", "--no-color", base, "HEAD", "--", path], cwd=root).stdout
    removed: list[tuple[int, str]] = []
    added: list[tuple[int, str]] = []
    old = new = 0
    for line in diff.splitlines():
        m = HUNK_RE.match(line)
        if m:
            old, new = int(m.group(1)), int(m.group(3))
            continue
        if line.startswith("-") and not line.startswith("---"):
            removed.append((old, line[1:]))
            old += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((new, line[1:]))
            new += 1
    return removed, added


def spec_offences(root: Path, base: str, path: str, heading: str) -> list[str]:
    old_lines = show(root, base, path)
    new_lines = show(root, "HEAD", path)
    if old_lines is None or new_lines is None:  # a spec added or deleted has no version to protect
        return []
    removed, added = changed_lines(root, base, path)
    old_rng = changelog_range(old_lines, heading)
    new_rng = changelog_range(new_lines, heading)
    found: dict[int, str] = {}
    for side, rng, rows in (("old", old_rng, removed), ("new", new_rng, added)):
        for no, text in rows:
            if VERSION_RE.match(text) or text.startswith("**Version:**"):
                found.setdefault(no, "%s:%d: the **Version:** line is changed" % (path, no))
            elif rng and rng[0] <= no <= rng[1]:
                found.setdefault(no, "%s:%d: the change log (\"%s\") is changed" % (path, no, heading))
    return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------
# notes
# --------------------------------------------------------------------------

class Note:
    def __init__(self, path: str, spec: str, kind: str, text: str):
        self.path, self.spec, self.kind, self.text = path, spec, kind, text


def parse_note(path: str, text: str) -> Note | str:
    """A Note, or the reason it is malformed (prefixed with file:line)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "%s:1: a change note starts with a '---' front matter line" % path
    meta: dict[str, str] = {}
    end = None
    for i, raw in enumerate(lines[1:], start=2):
        if raw.strip() == "---":
            end = i
            break
        line = re.sub(r"\s+#.*$", "", raw).strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            return "%s:%d: expected 'key: value' in the front matter" % (path, i)
        meta[key.strip()] = value.strip().strip("'\"")
    if end is None:
        return "%s:%d: the front matter is not closed with '---'" % (path, len(lines))
    spec = meta.get("spec", "")
    if not spec:
        return "%s:1: front matter needs 'spec: <path of the spec file>'" % path
    kind = meta.get("change", "")
    if kind not in KINDS:
        return "%s:1: 'change' must be one of %s (found '%s')" % (path, ", ".join(KINDS), kind)
    body = " ".join(" ".join(lines[end:]).split())
    if not body:
        return "%s:%d: the note has no text for the change log" % (path, end)
    return Note(path, dc.posix(spec), kind, body)


def read_notes(root: Path) -> tuple[list[Note], list[str]]:
    notes: list[Note] = []
    problems: list[str] = []
    folder = root / NOTES_DIR
    if not folder.is_dir():
        return notes, problems
    for f in sorted(folder.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        rel = "%s/%s" % (NOTES_DIR, f.name)
        got = parse_note(rel, f.read_text(encoding="utf-8-sig"))
        (problems if isinstance(got, str) else notes).append(got)
    return notes, problems


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    root = dc.repo_root()
    cfg = dc.load_gate(root)
    problems = read_notes(root)[1]
    names = branch_names(root, args.branch)
    release = is_release_branch(names, cfg)
    if not release:
        base_ref = args.base_ref or "origin/" + cfg["default_branch"]
        if dc.rev(base_ref, root) is None:
            raise dc.DeliveryError("base ref '%s' not found. Run 'git fetch' or pass --base-ref." % base_ref)
        mb = dc.run_git(["merge-base", "HEAD", base_ref], cwd=root, check=False)
        if mb.returncode != 0 or not mb.stdout.strip():
            raise dc.DeliveryError("HEAD and '%s' have no common ancestor" % base_ref)
        base = mb.stdout.strip()
        for path in dc.changed_files(base, root):
            if re.match(r"(?i)^changelog", path.rsplit("/", 1)[-1]):
                problems.append("%s: a changelog file is changed" % path)
            elif is_spec(path, cfg):
                problems += spec_offences(root, base, path, cfg["changelog_heading"])
    if problems:
        print("change-notes: FAIL")
        for p in problems:
            print("  " + p)
        if not release:
            print("Do not edit a spec's version or change log, or a CHANGELOG file, on a feature branch.")
            print("Add a change note instead: %s/<task-id>-<slug>.md with 'spec:' and 'change: patch|minor|major'." % NOTES_DIR)
            print("It is folded into the version and the change log on the release branch (change_notes.py fold).")
        return dc.EXIT_FAIL
    print("change-notes: ok (%s)" % ("release branch" if release else "no version, change-log or CHANGELOG edits"))
    return dc.EXIT_OK


# --------------------------------------------------------------------------
# fold
# --------------------------------------------------------------------------

def bump(version: tuple[int, int, int], kind: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if kind == "major":
        return major + 1, 0, 0
    if kind == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def plan_spec(root: Path, cfg: dict, spec: str, notes: list[Note], date: str) -> tuple[str, str, str, str]:
    """(new text, old version, new version, highest kind) for one spec."""
    path = root / spec
    if not path.is_file():
        raise dc.DeliveryError("%s: note spec '%s' does not exist" % (notes[0].path, spec))
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    idx = next((i for i, l in enumerate(lines) if VERSION_RE.match(l)), None)
    if idx is None:
        raise dc.DeliveryError("%s: no '**Version:** X.Y.Z' line to bump" % spec)
    m = VERSION_RE.match(lines[idx])
    old = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    kind = max((n.kind for n in notes), key=KINDS.index)
    new = bump(old, kind)
    new_s = "%d.%d.%d" % new
    lines[idx] = "%s%s%s" % (m.group(1), new_s, m.group(5))
    rng = changelog_range(lines, cfg["changelog_heading"])
    if rng is None:
        raise dc.DeliveryError("%s: no change-log heading starting '%s'" % (spec, cfg["changelog_heading"]))
    entry = ["", "**%s — %s.**" % (new_s, date), ""] + ["- " + n.text for n in notes]
    at = rng[0]  # right under the heading (rng[0] is its 1-based line)
    if at < len(lines) and lines[at].strip():
        entry.append("")
    lines[at:at] = entry
    return eol.join(lines), "%d.%d.%d" % old, new_s, kind


def cmd_fold(args: argparse.Namespace) -> int:
    root = dc.repo_root()
    cfg = dc.load_gate(root)
    notes, problems = read_notes(root)
    if problems:
        print("change-notes: cannot fold")
        for p in problems:
            print("  " + p)
        return dc.EXIT_FAIL
    if not notes:
        print("change-notes: no notes in %s/; nothing to fold" % NOTES_DIR)
        return dc.EXIT_OK
    date = args.date or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    by_spec: dict[str, list[Note]] = {}
    for n in notes:
        by_spec.setdefault(n.spec, []).append(n)
    plans = {spec: plan_spec(root, cfg, spec, group, date) for spec, group in sorted(by_spec.items())}
    verb = "would fold" if args.dry_run else "folded"
    for spec, (text, old, new, kind) in plans.items():
        group = by_spec[spec]
        print("%s %d note%s into %s: %s -> %s (%s), entry dated %s" % (
            verb, len(group), "" if len(group) == 1 else "s", spec, old, new, kind, date))
        for n in group:
            print("  - %s: %s" % (n.path, n.text))
        if not args.dry_run:
            with open(root / spec, "w", encoding="utf-8", newline="") as f:
                f.write(text)
    if not args.dry_run:
        for n in notes:
            (root / n.path).unlink()
    return dc.EXIT_OK


def main() -> int:
    ap = argparse.ArgumentParser(description="Check and fold spec change notes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="fail on a version or change-log edit off a release branch")
    c.add_argument("--base-ref", help="base to diff against (default origin/<default_branch>); the merge base is used")
    c.add_argument("--branch", help="branch name to judge (default: the checked-out branch)")
    c.set_defaults(fn=cmd_check)
    f = sub.add_parser("fold", help="fold the notes into versions and change logs")
    f.add_argument("--dry-run", action="store_true", help="print what would be done; write nothing")
    f.add_argument("--date", help="date of the entries (default: today, UTC)")
    f.set_defaults(fn=cmd_fold)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    dc.main_guard(main)
