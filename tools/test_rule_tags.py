#!/usr/bin/env python3
"""Every rule line shipped to projects names what enforces it (STACKSPEC 13.8, "Rules name their check").

A rule file is any `rules/*.md` a plugin ships (outside docs/). Each rule line, a `- ` bullet,
ends with exactly one tag:

    <!-- check: <path>[#<function or step>] -->   the named code refuses or reports the rule
    <!-- check: DL-37, Q-2 -->                     the named DELIVERYSPEC ids enforce it (ids must exist in the spec)
    <!-- advice -->                               nothing enforces it

This test fails on an untagged bullet, on a `check:` path that does not exist in the repository
(paths are relative to the repository root), and on a `#name` that the file does not mention.
The one exception: the TC9 guard scripts/delivery/session_guard.py may be absent on a branch that
has not joined TC9 yet; its tags are then skipped with a message, never silently passed.

Run:  python3 tools/test_rule_tags.py
Exit: 0 all passed, 1 otherwise.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parent.parent
TAG_RE = re.compile(r"<!-- (advice|check: (.+?)) -->$")
ID_RE = re.compile(r"^(DL-\d\d|Q-\d+)$")
SPEC = "docs/specs/delivery/DELIVERYSPEC.md"
BULLET_RE = re.compile(r"^\s*[-*] ")
LATE = ("claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery/session_guard.py",)
EXPECTED = (
    "claude/plugins/artifacts/rules/project-artifacts.md",
    "claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/agents-and-integration.md",
    "claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/clarifying-questions.md",
    "claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/delivery-timing.md",
)


def spec_ids(text: str | None = None) -> set[str]:
    """Ids DELIVERYSPEC defines: DL-nn rows of section 1 and the Q-n lines of decision D8."""
    if text is None:
        text = (REPO / SPEC).read_text(encoding="utf-8")
    return set(re.findall(r"^\| (DL-\d\d) \|", text, re.M)) | set(re.findall(r"^\s*- (Q-\d+) ", text, re.M))


def rule_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout.decode("utf-8")
    files = [f for f in out.split("\0") if re.search(r"(^|/)rules/[^/]+\.md$", f) and not f.startswith("docs/")]
    return sorted(f for f in files if (REPO / f).is_file())


def problems(rel: str, text: str, exists=None, ids: set[str] | None = None) -> list[str]:
    """Findings for one rule file's text. `exists` replaces the file check in the self-tests."""
    found: list[str] = []
    for no, line in enumerate(text.splitlines(), 1):
        if not BULLET_RE.match(line):
            continue
        m = TAG_RE.search(line.rstrip())
        if not m:
            found.append("%s:%d: rule line has no `<!-- check: ... -->` or `<!-- advice -->` tag" % (rel, no))
            continue
        if m.group(1) == "advice":
            continue
        if ID_RE.match(m.group(2).split(",")[0].strip()):
            known = spec_ids() if ids is None else ids
            for one in (i.strip() for i in m.group(2).split(",")):
                if not ID_RE.match(one):
                    found.append("%s:%d: malformed id in check tag: %s" % (rel, no, one))
                elif one not in known:
                    found.append("%s:%d: check id %s is not in %s" % (rel, no, one, SPEC))
            continue
        path, _, name = m.group(2).partition("#")
        if exists is not None:
            if not exists(path):
                found.append("%s:%d: check path does not exist: %s" % (rel, no, path))
            continue
        target = REPO / path
        if not target.is_file():
            if path in LATE:
                print("skip %s:%d: %s does not exist on this branch yet (TC9 guard; must exist when the train joins)" % (rel, no, path))
                continue
            found.append("%s:%d: check path does not exist: %s" % (rel, no, path))
        elif name and name not in target.read_text(encoding="utf-8", errors="replace"):
            found.append("%s:%d: %s does not mention %s" % (rel, no, path, name))
    return found


def selftest() -> list[str]:
    """The checks above must be able to fail."""
    bad: list[str] = []
    if not problems("x.md", "- a rule\n"):
        bad.append("an untagged bullet was not reported")
    if problems("x.md", "- a rule <!-- advice -->\n"):
        bad.append("an advice tag was refused")
    if not problems("x.md", "- a rule <!-- check: nope/missing.py -->\n"):
        bad.append("a check path that does not exist was not reported")
    if not problems("x.md", "- a rule <!-- check: tools/test_rule_tags.py#" + "no_such" + "_name -->\n"):
        bad.append("a #name the file does not mention was not reported")
    if problems("x.md", "- a rule <!-- check: tools/test_rule_tags.py#problems -->\n"):
        bad.append("a valid check tag was refused")
    fake = {"DL-01", "Q-1"}
    if problems("x.md", "- a rule <!-- check: DL-01, Q-1 -->\n", ids=fake):
        bad.append("a valid id tag was refused")
    if not problems("x.md", "- a rule <!-- check: DL-99 -->\n", ids=fake):
        bad.append("an id missing from the spec was not reported")
    if not problems("x.md", "- a rule <!-- check: DL-01, nonsense -->\n", ids=fake):
        bad.append("a malformed id in a list was not reported")
    if not {"DL-31", "DL-74", "Q-2", "Q-5"} <= spec_ids():
        bad.append("DELIVERYSPEC ids were not read")
    if not problems("x.md", "- a rule <!-- advice --> trailing\n"):
        bad.append("a tag that is not at the end of the line was accepted")
    return bad


def main() -> int:
    bad = [("self-test", m) for m in selftest()]
    files = rule_files()
    for need in EXPECTED:
        if need not in files:
            bad.append((need, "expected rule file is not tracked"))
    total = tagged = 0
    for rel in files:
        text = (REPO / rel).read_text(encoding="utf-8")
        total += sum(1 for ln in text.splitlines() if BULLET_RE.match(ln))
        found = problems(rel, text)
        tagged += sum(1 for ln in text.splitlines() if BULLET_RE.match(ln) and TAG_RE.search(ln.rstrip()))
        bad += [(rel, f) for f in found]
        print("%s %s" % ("FAIL" if found else "ok  ", rel))
    for where, msg in bad:
        print("  " + msg)
    print("\n%s: %d rule lines in %d files, %d tagged" % ("PASSED" if not bad else "FAILED (%d)" % len(bad), total, len(files), tagged))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
