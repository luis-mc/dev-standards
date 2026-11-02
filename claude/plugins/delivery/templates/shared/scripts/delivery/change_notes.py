#!/usr/bin/env python3
"""Change notes: how a spec's version and change log are kept by one hand (CONTRACT.md U7).

    change_notes.py check [--config PATH] [--base-ref REF] [--branch NAME]
    change_notes.py fold  [--config PATH] [--dry-run] [--date YYYY-MM-DD]
    change_notes.py pending [--config PATH]

A change note is docs/specs/changes/<task-id>-<slug>.md:

    ---
    spec: docs/architecture/stack-profile.md
    plugin: plugins/tools/.claude-plugin/plugin.json   # optional; a note names a spec, a plugin, or both
    change: minor            # patch | minor | major
    ---
    One or two sentences for the change log.

check (a gate.json step, scope "always", pre_push): on a branch that is not a
release branch, fails when the diff against the base (the merge base with REF)
changes a spec's **Version:** line or its change-log section, a plugin
manifest's "version" line, or any CHANGELOG* file; each offence is named as file:line with the fix (add a change note
instead). It also fails on a malformed note. On a release branch only the notes
are checked. With "plugin_notes_required" set, it also fails (branch diff only, not
--staged) when the diff changes a file of a plugin (the folder holding its
.claude-plugin/plugin.json) and no note names that plugin's manifest; paths matching
"plugin_note_exempt" globs (tests, say) need no note.

pending (run on every push to the default branch): fails while any note waits to
be folded, so a note merged without a fold cannot leave a plugin or spec at its
old version unnoticed.

fold (run on a release branch before the ready PR): for each spec with notes,
bumps its **Version:** by the highest change kind, writes one change-log entry
under the change-log heading (new version, date, one bullet per note) and
deletes the folded notes. A note's "plugin:" is bumped the same way: the
manifest's "version" value, by the highest kind of the notes naming it (no change
log). No notes: nothing to do. --dry-run prints the same
summary and writes nothing.

Settings come from scripts/delivery/gate.json, or from --config PATH (a JSON
file relative to the repository root; no "schema" or steps needed). Keys, all
optional: "specs" (globs; default docs/specs/*.md), "changelog_heading" (a heading
starting with this text; default "What changed"), "changelog_headings" (an object
spec path -> heading overriding that for one spec; "" means the spec has no change
log, so only its version is guarded and bumped), "plugins" (globs of plugin
manifests whose "version" is guarded; default none), "release_branches" (globs;
default *-integration and release/*), "default_branch" (default main),
"plugin_notes_required" (default false), "plugin_note_exempt" (globs; default none).

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
PLUGIN_VERSION_RE = re.compile(r'^(\s*"version"\s*:\s*")(\d+)\.(\d+)\.(\d+)(".*)$')
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


def load_config(root: Path, config: str | None) -> dict:
    """gate.json (default), or the small JSON file --config names. Fills defaults."""
    if config:
        path = root / config
        if not path.is_file():
            raise dc.DeliveryError("%s not found" % config)
        try:
            cfg = dc.read_json(path)
        except (OSError, ValueError) as exc:
            raise dc.DeliveryError("%s is not valid JSON: %s" % (config, exc)) from None
        if not isinstance(cfg, dict):
            raise dc.DeliveryError("%s: expected a JSON object" % config)
        where = config
        cfg.setdefault("default_branch", "main")
        if not isinstance(cfg["default_branch"], str) or not cfg["default_branch"]:
            raise dc.DeliveryError("%s: 'default_branch' must be a non-empty string" % where)
        cfg.setdefault("specs", ["docs/specs/*.md"])
        cfg.setdefault("release_branches", ["*-integration", "release/*"])
        cfg.setdefault("changelog_heading", "What changed")
        if not isinstance(cfg["changelog_heading"], str) or not cfg["changelog_heading"].strip():
            raise dc.DeliveryError("%s: 'changelog_heading' must be a non-empty string" % where)
        for key in ("specs", "release_branches"):
            cfg[key] = dc._str_list(cfg, key, where)
    else:
        cfg = dc.load_gate(root)
        where = dc.GATE_JSON_PATH
    cfg["plugins"] = dc._str_list(cfg, "plugins", where)
    notes_dir = cfg.setdefault("notes_dir", NOTES_DIR)
    if not isinstance(notes_dir, str) or not notes_dir.strip("/") or notes_dir.startswith("/") or ".." in notes_dir.split("/"):
        raise dc.DeliveryError("%s: 'notes_dir' must be a relative folder inside the repository" % where)
    cfg["notes_dir"] = dc.posix(notes_dir).strip("/")
    heads = cfg.setdefault("changelog_headings", {})
    if not isinstance(heads, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in heads.items()):
        raise dc.DeliveryError("%s: 'changelog_headings' must be an object of spec path to heading" % where)
    cfg["changelog_headings"] = {dc.posix(k): v for k, v in heads.items()}
    return cfg


def heading_for(cfg: dict, spec: str) -> str:
    """The change-log heading of one spec ('' when it has none)."""
    return cfg["changelog_headings"].get(spec, cfg["changelog_heading"])


def is_plugin(path: str, cfg: dict) -> bool:
    return any(glob_to_re(g).match(path) for g in cfg["plugins"])


def is_spec(path: str, cfg: dict) -> bool:
    if path.startswith(cfg["notes_dir"] + "/"):
        return False
    return any(glob_to_re(g).match(path) for g in cfg["specs"])


def plugin_dir(manifest: str) -> str:
    """The folder a plugin manifest belongs to, with a trailing slash: the parent of .claude-plugin/."""
    parts = manifest.split("/")[:-1]
    if parts and parts[-1] == ".claude-plugin":
        parts = parts[:-1]
    return "/".join(parts) + "/" if parts else ""


def missing_plugin_notes(root: Path, cfg: dict, paths: list[str], notes: list["Note"]) -> list[str]:
    """One offence per plugin whose files the change touches with no note naming its manifest."""
    if not cfg.get("plugin_notes_required"):
        return []
    exempt = [glob_to_re(g) for g in cfg.get("plugin_note_exempt") or []]
    noted = {n.plugin for n in notes}
    manifests = sorted({p.relative_to(root).as_posix() for g in cfg["plugins"] for p in root.glob(g) if p.is_file()})
    found = []
    for manifest in manifests:
        folder = plugin_dir(manifest)
        touched = [p for p in paths if p.startswith(folder) and not any(e.match(p) for e in exempt)]
        if touched and manifest not in noted:
            found.append("%s: %d file%s changed (%s) and no change note names %s" % (
                folder.rstrip("/"), len(touched), "" if len(touched) == 1 else "s", touched[0], manifest))
    return found


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


def changed_lines(root: Path, base: str, path: str, new: str = "HEAD") -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(removed, added) lines of one file between base and `new` (a ref, or "" for the index): (line number, text)."""
    ends = [base, new] if new else ["--cached", base]
    diff = dc.run_git(["diff", "-U0", "--no-renames", "--no-color", *ends, "--", path], cwd=root).stdout
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


def spec_offences(root: Path, base: str, path: str, heading: str, new: str = "HEAD") -> list[str]:
    old_lines = show(root, base, path)
    new_lines = show(root, new, path)
    if old_lines is None or new_lines is None:  # a spec added or deleted has no version to protect
        return []
    removed, added = changed_lines(root, base, path, new)
    old_rng = changelog_range(old_lines, heading) if heading else None
    new_rng = changelog_range(new_lines, heading) if heading else None
    found: dict[int, str] = {}
    for side, rng, rows in (("old", old_rng, removed), ("new", new_rng, added)):
        for no, text in rows:
            if VERSION_RE.match(text) or text.startswith("**Version:**"):
                found.setdefault(no, "%s:%d: the **Version:** line is changed" % (path, no))
            elif rng and rng[0] <= no <= rng[1]:
                found.setdefault(no, "%s:%d: the change log (\"%s\") is changed" % (path, no, heading))
    return [found[k] for k in sorted(found)]


def plugin_offences(root: Path, base: str, path: str, new: str = "HEAD") -> list[str]:
    """A plugin manifest's "version" line changed (a file added or deleted has none to protect)."""
    if show(root, base, path) is None or show(root, new, path) is None:
        return []
    removed, added = changed_lines(root, base, path, new)
    found = {no: "%s:%d: the plugin \"version\" line is changed" % (path, no)
             for no, text in removed + added if PLUGIN_VERSION_RE.match(text)}
    return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------
# notes
# --------------------------------------------------------------------------

class Note:
    def __init__(self, path: str, spec: str, plugin: str, kind: str, text: str):
        self.path, self.spec, self.plugin, self.kind, self.text = path, spec, plugin, kind, text


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
    plugin = meta.get("plugin", "")
    if not spec and not plugin:
        return "%s:1: front matter needs 'spec: <path of the spec file>' or 'plugin: <path of plugin.json>'" % path
    kind = meta.get("change", "")
    if kind not in KINDS:
        return "%s:1: 'change' must be one of %s (found '%s')" % (path, ", ".join(KINDS), kind)
    body = " ".join(" ".join(lines[end:]).split())
    if not body:
        return "%s:%d: the note has no text for the change log" % (path, end)
    return Note(path, dc.posix(spec) if spec else "", dc.posix(plugin) if plugin else "", kind, body)


def read_notes(root: Path, cfg: dict) -> tuple[list[Note], list[str]]:
    notes: list[Note] = []
    problems: list[str] = []
    folder = root / cfg["notes_dir"]
    if not folder.is_dir():
        return notes, problems
    for f in sorted(folder.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        rel = "%s/%s" % (cfg["notes_dir"], f.name)
        got = parse_note(rel, f.read_text(encoding="utf-8-sig"))
        (problems if isinstance(got, str) else notes).append(got)
    return notes, problems


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def path_offences(root: Path, cfg: dict, base: str, new: str, path: str) -> list[str]:
    """What one changed path breaks: a CHANGELOG file, a spec's version or change log, a plugin's version.
    `new` is the ref the change ends at, or "" for the index (the staged changes)."""
    if re.match(r"(?i)^changelog", path.rsplit("/", 1)[-1]):
        return ["%s: a changelog file is changed" % path]
    if is_spec(path, cfg):
        return spec_offences(root, base, path, heading_for(cfg, path), new)
    if is_plugin(path, cfg):
        return plugin_offences(root, base, path, new)
    return []


def cmd_check(args: argparse.Namespace) -> int:
    root = dc.repo_root()
    cfg = load_config(root, args.config)
    notes, problems = read_notes(root, cfg)
    names = branch_names(root, args.branch)
    release = is_release_branch(names, cfg)
    if not release and args.staged:
        # The index against HEAD: what the commit about to be made changes. No base ref, no fetch.
        if dc.rev("HEAD", root) is not None:  # a repository with no commit yet has nothing to protect
            out = dc.run_git(["diff", "--cached", "--name-only", "--no-renames", "-z"], cwd=root).stdout
            for path in sorted(f for f in out.split(chr(0)) if f):
                problems += path_offences(root, cfg, "HEAD", "", path)
    elif not release:
        base_ref = args.base_ref or "origin/" + cfg["default_branch"]
        if dc.rev(base_ref, root) is None:
            raise dc.DeliveryError("base ref '%s' not found. Run 'git fetch' or pass --base-ref." % base_ref)
        mb = dc.run_git(["merge-base", "HEAD", base_ref], cwd=root, check=False)
        if mb.returncode != 0 or not mb.stdout.strip():
            raise dc.DeliveryError("HEAD and '%s' have no common ancestor" % base_ref)
        base = mb.stdout.strip()
        paths = list(dc.changed_files(base, root))
        for path in paths:
            problems += path_offences(root, cfg, base, "HEAD", path)
        problems += missing_plugin_notes(root, cfg, paths, notes)
    if problems:
        print("change-notes: FAIL")
        for p in problems:
            print("  " + p)
        if not release:
            print("Do not edit a spec's or plugin's version, a spec's change log, or a CHANGELOG file, on a feature branch.")
            print("Add a change note instead (and one for each changed plugin): %s/<task-id>-<slug>.md with 'spec:' (or 'plugin:') and 'change: patch|minor|major'." % cfg["notes_dir"])
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
    heading = heading_for(cfg, spec)
    if heading:  # a spec that names no change-log heading has only its version bumped
        rng = changelog_range(lines, heading)
        if rng is None:
            raise dc.DeliveryError("%s: no change-log heading starting '%s'" % (spec, heading))
        entry = ["", "**%s — %s.**" % (new_s, date), ""] + ["- " + n.text for n in notes]
        at = rng[0]  # right under the heading (rng[0] is its 1-based line)
        if at < len(lines) and lines[at].strip():
            entry.append("")
        lines[at:at] = entry
    return eol.join(lines), "%d.%d.%d" % old, new_s, kind


def plan_plugin(root: Path, plugin: str, notes: list[Note]) -> tuple[str, str, str, str]:
    """(new text, old version, new version, highest kind) for one plugin manifest."""
    path = root / plugin
    if not path.is_file():
        raise dc.DeliveryError("%s: note plugin '%s' does not exist" % (notes[0].path, plugin))
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    idx = next((i for i, l in enumerate(lines) if PLUGIN_VERSION_RE.match(l)), None)
    if idx is None:
        raise dc.DeliveryError("%s: no '\"version\": \"X.Y.Z\"' line to bump" % plugin)
    m = PLUGIN_VERSION_RE.match(lines[idx])
    old = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    kind = max((n.kind for n in notes), key=KINDS.index)
    new_s = "%d.%d.%d" % bump(old, kind)
    lines[idx] = "%s%s%s" % (m.group(1), new_s, m.group(5))
    return eol.join(lines), "%d.%d.%d" % old, new_s, kind


def cmd_fold(args: argparse.Namespace) -> int:
    root = dc.repo_root()
    cfg = load_config(root, args.config)
    notes, problems = read_notes(root, cfg)
    if problems:
        print("change-notes: cannot fold")
        for p in problems:
            print("  " + p)
        return dc.EXIT_FAIL
    if not notes:
        print("change-notes: no notes in %s/; nothing to fold" % cfg["notes_dir"])
        return dc.EXIT_OK
    date = args.date or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    by_spec: dict[str, list[Note]] = {}
    by_plugin: dict[str, list[Note]] = {}
    for n in notes:
        if n.spec:
            by_spec.setdefault(n.spec, []).append(n)
        if n.plugin:
            by_plugin.setdefault(n.plugin, []).append(n)
    plans = {spec: plan_spec(root, cfg, spec, group, date) for spec, group in sorted(by_spec.items())}
    plans.update({plugin: plan_plugin(root, plugin, group) for plugin, group in sorted(by_plugin.items())})
    verb = "would fold" if args.dry_run else "folded"
    for spec, (text, old, new, kind) in plans.items():
        group = by_spec.get(spec) or by_plugin[spec]
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


def cmd_pending(args: argparse.Namespace) -> int:
    root = dc.repo_root()
    cfg = load_config(root, args.config)  # a broken config is a usage error here too
    notes, problems = read_notes(root, cfg)
    waiting = [n.path for n in notes] + problems
    if waiting:
        print("change-notes: %d note%s wait to be folded; the versions they name are not raised yet" % (
            len(waiting), "" if len(waiting) == 1 else "s"))
        for w in waiting:
            print("  " + w)
        print("Fold them: change_notes.py fold (on a release branch), then push.")
        return dc.EXIT_FAIL
    print("change-notes: nothing waits to be folded")
    return dc.EXIT_OK


def main() -> int:
    ap = argparse.ArgumentParser(description="Check and fold spec change notes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    conf = argparse.ArgumentParser(add_help=False)
    conf.add_argument("--config", help="settings JSON (relative to the repository root) used instead of scripts/delivery/gate.json")
    c = sub.add_parser("check", parents=[conf], help="fail on a version or change-log edit off a release branch")
    c.add_argument("--base-ref", help="base to diff against (default origin/<default_branch>); the merge base is used")
    c.add_argument("--staged", action="store_true", help="judge the staged changes (index against HEAD), as the pre-commit hook does; no base ref")
    c.add_argument("--branch", help="branch name to judge (default: the checked-out branch)")
    c.set_defaults(fn=cmd_check)
    f = sub.add_parser("fold", parents=[conf], help="fold the notes into versions and change logs")
    f.add_argument("--dry-run", action="store_true", help="print what would be done; write nothing")
    f.add_argument("--date", help="date of the entries (default: today, UTC)")
    f.set_defaults(fn=cmd_fold)
    w = sub.add_parser("pending", parents=[conf], help="fail while any note waits to be folded")
    w.set_defaults(fn=cmd_pending)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    dc.main_guard(main)
