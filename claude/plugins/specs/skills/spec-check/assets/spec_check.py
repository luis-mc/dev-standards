#!/usr/bin/env python3
"""
Structural checker for the binding specs — numbering and internal references.

One script, one job: everything about how a spec is *numbered* and how its
internal pointers *resolve*. It is spec-agnostic and runs over every spec, so
`invariants.md` and `authentication.md` are held to the same structural rules
even though only one of them declares requirement identifiers.

It replaces `spec_refcheck.py` (section references only) and absorbs the
identifier check from what is now `authspec_check.py`. Those two validated
*different namespaces* that look alike — `§19.4` points at a heading, `R19.25`
points at a requirement definition — and having them in separate scripts made it
easy to believe one covered the other. It does not: a spec can have every
§-reference resolve while citing a requirement that was never defined. Both live
here now.

`authspec_check.py` keeps what is genuinely AUTHSPEC-specific: attribute names,
enum values, route/bucket maps, retention rows, erasure coverage. Those need that
document's §4 entity tables and cannot be asked of an arbitrary spec.

WHAT IS CHECKED
---------------
headings     H1 no two headings carry the same number
             H2 heading depth matches its dotted components (`### 12.3`)
             H3 every subsection has a parent heading
             H4 sibling numbers are contiguous                    [warning]
             H5 headings appear in ascending order

identifiers  I1 each `**Rn.n**` is defined exactly once
             I2 an identifier's prefix matches its enclosing section
             I3 identifiers are contiguous within a section        [warning]
             I4 identifiers appear in ascending order
             I5 no malformed identifier (`R6.6.1` is a section ref, not an ID)

references   X1a every bare `§n.n` resolves to a heading here
             X1b every `NAME §n.n` resolves to a heading in NAME
             X2  every `Rn.n` citation resolves to a definition

INTERNAL VS OUTBOUND REFERENCES
-------------------------------
A bare `§9` points at this document. `STACKSPEC §9` points at another one, and
resolving it locally is how a conformance document — a product's Stack Profile,
whose references are almost all outbound — ends up validated against itself.

That produced two failures at once. The loud one was 23 false errors. The
dangerous one was silent: profile §9 is "Data classification and retention"
while STACKSPEC §9 is "Object storage", so a citation of the latter resolved
against the former and reported clean. Six numbers collided that way.

Registered documents (`EXTERNAL_SPECS`, extended with `--external NAME=PATH`)
are resolved against the real target, so an outbound citation is checked rather
than skipped. Only registered names count: capitalised words precede section
marks for ordinary reasons — "MUST NOT contain PII (§16.4)" is an internal
reference, not a citation of a document called PII — so an unknown prefix falls
through to the internal path and is merely mentioned in the error if that fails
too.

WHY GAPS ARE WARNINGS AND NOT ERRORS
------------------------------------
H4 and I3 report gaps rather than failing on them, because numbering here is
append-only by design. A citation is a stable reference: renumbering §3 to §2
after deleting §2 invalidates every `R3.x` identifier and every cross-reference
that pointed at them. Deleting the section and *leaving the gap* is the correct
move, and the gap is the evidence of that discipline. It is still surfaced,
because an unintended gap looks identical to a deliberate one and only the
author can tell them apart.

Usage:
    python3 tools/spec_check.py                    # every spec under references/
    python3 tools/spec_check.py path/to/spec.md    # one named spec
    python3 tools/spec_check.py --strict           # warnings become failures
    python3 tools/spec_check.py --json
    python3 tools/spec_check.py doc.md --external OTHERSPEC=path/to/other.md

Exit codes:
    0  no errors (warnings may be present unless --strict)
    1  at least one error, or any finding under --strict
    2  a document could not be read
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ERROR = "error"
WARNING = "warning"

# Each binding spec is owned by the skill that acts on it, so they no longer
# share a directory: STACKSPEC belongs to tech-stack-setup, AUTHSPEC to
# auth-setup. Two constants rather than one join, because a single "the
# references directory" is exactly the assumption that broke when the skills
# were split.
_SKILLS = "claude/plugins/project-setup/skills"
_STACKSPEC = f"{_SKILLS}/tech-stack-setup/references/invariants.md"
_AUTHSPEC = f"{_SKILLS}/auth-setup/references/authentication.md"

DEFAULT_SPECS = (
    _STACKSPEC,
    _AUTHSPEC,
)

# `## 12. Title`, `### 12.3 Title`, `#### 12.3.1 Title`. The trailing letter is
# accepted so a future `### 12.3a` reads as a heading rather than as nothing.
HEADING_RE = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*[a-z]?)\.?\s+(.*)$")

# A definition is a bolded identifier followed by a dash. A citation inside a
# table cell or a coverage map is bolded but not dash-terminated, which is what
# keeps the two apart.
DEF_RE = re.compile(r"\*\*(R(\d+)\.(\d+)([a-z]?))\*\*\s*[—–-]")

# Capture every dotted component so a malformed three-part identifier such as
# `R6.6.1` surfaces instead of silently truncating to a valid `R6.6`.
CITE_RE = re.compile(r"\bR(\d+(?:\.\d+)+[a-z]?)\b")

# `§6.6`, `§ 6.6`, `§164.312`, `§12.3a`.
SECREF_RE = re.compile(r"§\s?(\d+(?:\.\d+)*[a-z]?)")

# A reference whose first component reaches three digits is a statutory citation
# (HIPAA §164.312, CCPA §1798.105), not an internal cross-reference. This is a
# flat floor, NOT "one past the highest heading": a ceiling derived from the
# document would silently reclassify a dangling §30 in a 29-section spec as
# statutory, which is precisely the bug this constant used to have.
STATUTORY_FLOOR = 100

_LETTERS = "abcdefghijklmnopqrstuvwxyz"

# Documents a spec may cite by name. A conformance document — a product's Stack
# Profile — is mostly *outbound* references: its `§n.n` point at STACKSPEC, not
# at its own headings. Resolving those locally is how such a document ends up
# validated against itself.
#
# Registered by name so the citation is actually checked. Skipping outbound
# references instead would trade 23 false errors for an unbounded number of
# unvalidated ones, which is the trade this checker exists to refuse.
EXTERNAL_SPECS = {
    "STACKSPEC": _STACKSPEC,
    "AUTHSPEC": _AUTHSPEC,
}

# How far back to look for a document name preceding a `§`. Long enough for
# "STACKSPEC " plus the backtick/paren punctuation these citations are usually
# wrapped in, short enough that a document name earlier in the sentence does
# not capture an unrelated later reference.
_DOC_LOOKBEHIND = 24
_DOC_NAME_RE = re.compile(r"([A-Z][A-Z0-9_]{2,})[\s`(\[]*$")


def _cited_document(line: str, at: int) -> str | None:
    """The document name immediately preceding a `§` at `at`, if any.

    Handles the forms these citations actually take — `STACKSPEC §17.4`,
    `` `STACKSPEC §17.4` ``, `(STACKSPEC §9)` — by ignoring the punctuation
    between the name and the section mark.
    """
    m = _DOC_NAME_RE.search(line[max(0, at - _DOC_LOOKBEHIND):at])
    return m.group(1) if m else None


@dataclass
class Finding:
    check: str
    level: str
    line: int
    message: str

    def render(self, path: str) -> str:
        tag = "ERROR" if self.level == ERROR else "warn "
        return f"  {tag}  {path}:{self.line}  {self.message}"


@dataclass
class Heading:
    number: str
    depth: int
    title: str
    line: int


@dataclass
class Definition:
    ident: str
    section: int
    index: int
    suffix: str
    line: int


def _split(part: str) -> tuple[int, str]:
    digits = part.rstrip(_LETTERS)
    return (int(digits) if digits else 0), part[len(digits):]


def _num_key(number: str) -> list:
    """Order `12`, `12.3`, `12.3a` numerically rather than lexically."""
    key: list = []
    for part in number.split("."):
        digits, suffix = _split(part)
        key += [digits, suffix]
    return key


def strip_html_comments(lines: list[str]) -> list[str]:
    """Blank out `<!-- ... -->` spans, preserving line numbering.

    Nothing normative lives in an HTML comment: it is where a template keeps its
    authoring instructions and where an author parks a note to a reviewer. Those
    routinely contain *illustrative* numbering — "write `R4.9a`, never `R6.6.1`"
    — which is not a citation of anything and must not be resolved as one.

    Fenced code blocks are deliberately NOT stripped. Specs cite real
    requirements inside tables and code samples, and skipping them would create
    exactly the blind spot this checker exists to close.
    """
    out = list(lines)
    inside = False
    for i, raw in enumerate(out):
        text, cursor = raw, 0
        result = []
        while cursor < len(text):
            if not inside:
                start = text.find("<!--", cursor)
                if start < 0:
                    result.append(text[cursor:])
                    break
                result.append(text[cursor:start])
                cursor, inside = start + 4, True
            else:
                end = text.find("-->", cursor)
                if end < 0:
                    break
                cursor, inside = end + 3, False
        out[i] = "".join(result)
    return out


class Spec:
    def __init__(self, text: str, externals: dict[str, set[str]] | None = None):
        self.lines = strip_html_comments(text.splitlines())
        self.headings = self._parse_headings()
        self.numbers = {h.number for h in self.headings}
        self.definitions = self._parse_definitions()
        self.top_level = self._map_top_level()
        # name -> that document's heading numbers, for outbound citations.
        self.externals: dict[str, set[str]] = externals or {}

    def _parse_headings(self) -> list[Heading]:
        out = []
        for idx, raw in enumerate(self.lines, start=1):
            m = HEADING_RE.match(raw)
            if m:
                out.append(Heading(m.group(2), len(m.group(1)), m.group(3), idx))
        return out

    def _parse_definitions(self) -> list[Definition]:
        out = []
        for idx, raw in enumerate(self.lines, start=1):
            for m in DEF_RE.finditer(raw):
                out.append(Definition(m.group(1), int(m.group(2)),
                                      int(m.group(3)), m.group(4), idx))
        return out

    def _map_top_level(self) -> list[str | None]:
        """For each line, the number of the enclosing depth-2 heading."""
        owner: list[str | None] = [None] * (len(self.lines) + 2)
        tops = [h for h in self.headings if h.depth == 2]
        for i, h in enumerate(tops):
            end = tops[i + 1].line - 1 if i + 1 < len(tops) else len(self.lines)
            for ln in range(h.line, end + 1):
                owner[ln] = h.number
        return owner

    def resolves(self, number: str) -> bool:
        if number in self.numbers:
            return True
        # §24.2a resolves to 24.2 when no lettered heading exists.
        return number.rstrip(_LETTERS) in self.numbers

    def defined_idents(self) -> set[str]:
        return {d.ident for d in self.definitions}


# --------------------------------------------------------------------------
# headings
# --------------------------------------------------------------------------

def check_headings(spec: Spec) -> list[Finding]:
    out: list[Finding] = []
    by_number: dict[str, list[int]] = defaultdict(list)
    for h in spec.headings:
        by_number[h.number].append(h.line)

    # H1 — uniqueness.
    for number, lines in by_number.items():
        if len(lines) > 1:
            where = ", ".join(str(n) for n in lines)
            out.append(Finding("headings", ERROR, lines[0],
                               f"heading number {number} is used "
                               f"{len(lines)} times (lines {where}) — a "
                               f"§{number} reference cannot resolve to one of them"))

    for h in spec.headings:
        # H2 — depth agrees with the numbering.
        components = len(h.number.split("."))
        if components + 1 != h.depth:
            out.append(Finding("headings", ERROR, h.line,
                               f"heading {h.number} is at depth {h.depth} "
                               f"({'#' * h.depth}) but its number has "
                               f"{components} component(s); expected depth "
                               f"{components + 1}"))
        # H3 — parent exists.
        if "." in h.number:
            parent = h.number.rsplit(".", 1)[0]
            if parent not in spec.numbers:
                out.append(Finding("headings", ERROR, h.line,
                                   f"heading {h.number} has no parent heading "
                                   f"{parent}"))

    # H4 — sibling contiguity. Warning: see the module docstring.
    siblings: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    for h in spec.headings:
        parent, _, last = h.number.rpartition(".")
        digits, suffix = _split(last)
        if not suffix:  # a lettered sibling is an insertion, not a gap
            siblings[parent].append((digits, h.number, h.line))
    for parent, items in siblings.items():
        seen = sorted(i for i, _, _ in items)
        lowest, highest = seen[0], seen[-1]
        missing = [n for n in range(lowest, highest + 1) if n not in seen]
        if missing:
            label = f"§{parent}." if parent else "top-level §"
            gaps = ", ".join(f"{label}{n}" for n in missing)
            out.append(Finding("headings", WARNING, items[0][2],
                               f"gap in {label}x numbering: {gaps} absent. "
                               f"Deliberate after a deletion — numbering is "
                               f"append-only so citations stay valid. Confirm "
                               f"it is not an accident."))

    # H5 — document order.
    prev = None
    for h in spec.headings:
        key = _num_key(h.number)
        if prev is not None and key < prev[0]:
            out.append(Finding("headings", ERROR, h.line,
                               f"heading {h.number} appears after "
                               f"{prev[1]} (line {prev[2]}) — headings must "
                               f"be in ascending order"))
        prev = (key, h.number, h.line)
    return out


# --------------------------------------------------------------------------
# identifiers
# --------------------------------------------------------------------------

def check_identifiers(spec: Spec) -> list[Finding]:
    out: list[Finding] = []
    by_ident: dict[str, list[int]] = defaultdict(list)
    for d in spec.definitions:
        by_ident[d.ident].append(d.line)

    # I1 — uniqueness.
    for ident, lines in by_ident.items():
        if len(lines) > 1:
            where = ", ".join(str(n) for n in lines)
            out.append(Finding("identifiers", ERROR, lines[0],
                               f"{ident} is defined {len(lines)} times "
                               f"(lines {where}); an identifier must name one "
                               f"requirement"))

    # I2 — prefix matches the enclosing section.
    for d in spec.definitions:
        owner = spec.top_level[d.line]
        if owner is not None and owner != str(d.section):
            out.append(Finding("identifiers", ERROR, d.line,
                               f"{d.ident} is defined inside §{owner}; an "
                               f"identifier's first component must be its "
                               f"section, so this should be R{owner}.<n> or "
                               f"move to §{d.section}"))

    # I3 — contiguity within a section. Warning: see the module docstring.
    by_section: dict[int, list[Definition]] = defaultdict(list)
    for d in spec.definitions:
        if not d.suffix:  # a lettered variant is an insertion, not a gap
            by_section[d.section].append(d)
    for section, items in sorted(by_section.items()):
        seen = sorted(d.index for d in items)
        missing = [n for n in range(1, seen[-1] + 1) if n not in seen]
        if missing:
            gaps = ", ".join(f"R{section}.{n}" for n in missing)
            out.append(Finding("identifiers", WARNING, items[0].line,
                               f"gap in §{section} identifier numbering: "
                               f"{gaps} absent. Expected after a requirement "
                               f"is retired — identifiers are never reused. "
                               f"Confirm it is not an accident."))

    # I4 — document order.
    prev = None
    for d in spec.definitions:
        key = (d.section, d.index, d.suffix)
        if prev is not None and key < prev[0]:
            out.append(Finding("identifiers", ERROR, d.line,
                               f"{d.ident} is defined after {prev[1]} "
                               f"(line {prev[2]}) — definitions must be in "
                               f"ascending order"))
        prev = (key, d.ident, d.line)
    return out


# --------------------------------------------------------------------------
# references
# --------------------------------------------------------------------------

def check_references(spec: Spec) -> list[Finding]:
    out: list[Finding] = []
    defined = spec.defined_idents()

    # X1 — section references, internal and outbound.
    for idx, raw in enumerate(spec.lines, start=1):
        for m in SECREF_RE.finditer(raw):
            ref = m.group(1)
            head, _ = _split(ref.split(".")[0])
            if head >= STATUTORY_FLOOR:
                continue  # statutory citation

            doc = _cited_document(raw, m.start())

            # X1b — outbound: `STACKSPEC §9` is a citation of another
            # document, and resolving it against THIS document's headings is
            # how a conformance doc ends up validated against itself. Worse
            # than noise: where the numbering collides, a reference to the
            # other spec's §9 resolves silently against a local §9 that means
            # something completely different, and reports clean.
            #
            # Only a REGISTERED name counts. Capitalised words sit in front of
            # section marks for ordinary reasons — "MUST NOT contain PII
            # (§16.4)" is an internal reference, not a citation of a document
            # called PII — so an unknown prefix falls through to the internal
            # path below rather than being trusted as a document name.
            if doc is not None and doc in spec.externals:
                if ref not in spec.externals[doc]:
                    out.append(Finding("references", ERROR, idx,
                                       f"{doc} §{ref} does not resolve to a "
                                       f"heading in {doc}"))
                continue

            # X1a — internal.
            if spec.resolves(ref):
                continue
            # Only offer a hint when it is actually actionable. An
            # unconditional "R{ref} may have been meant" reads as though this
            # check validates identifiers, which it does not.
            if f"R{ref}" in defined:
                hint = f" — a requirement reference to R{ref} may have been meant"
            elif doc is not None:
                # Failed locally *and* carries an unregistered prefix: the most
                # likely reading is a citation of a document nothing registered.
                hint = (f" — preceded by {doc!r}; if that names another "
                        f"document, register it with --external {doc}=<path>")
            else:
                hint = ""
            out.append(Finding("references", ERROR, idx,
                               f"§{ref} does not resolve to a heading{hint}"))

    # X2 — identifier citations. Only meaningful where the document defines
    # identifiers at all; a spec that declares none cites none, and every
    # `Rn.n`-looking token in it would be a false positive.
    if not defined:
        return out
    for idx, raw in enumerate(spec.lines, start=1):
        for comps in CITE_RE.findall(raw):
            ident = "R" + comps
            trimmed = comps.rstrip(_LETTERS)
            # I5 — malformed identifier.
            if len(trimmed.split(".")) > 2:
                out.append(Finding("references", ERROR, idx,
                                   f"{ident} is malformed — a requirement "
                                   f"identifier has two components; this looks "
                                   f"like a section reference written with an "
                                   f"R prefix (§{comps})"))
                continue
            if ident not in defined:
                out.append(Finding("references", ERROR, idx,
                                   f"{ident} is cited but never defined"))
    return out


FAMILIES = [
    ("headings",    "numbering integrity of headings",       check_headings),
    ("identifiers", "numbering integrity of requirement IDs", check_identifiers),
    ("references",  "internal references resolve",            check_references),
]


def run(spec: Spec, only: str | None) -> list[tuple[str, str, str, list[Finding]]]:
    results = []
    for name, title, fn in FAMILIES:
        if only and only != name:
            continue
        # A spec with no identifiers is a legitimate state, not a defect —
        # STACKSPEC has none. Report it as n/a WITH the count, so nobody reads
        # a clean run as "the identifiers were validated".
        if name == "identifiers" and not spec.definitions:
            results.append((name, title, "n/a", []))
            continue
        results.append((name, title, "checked", fn(spec)))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Numbering and internal-reference checker for the specs.")
    ap.add_argument("specs", nargs="*", type=Path,
                    help="paths to specification markdown "
                         "(default: every spec under references/)")
    ap.add_argument("--only", default=None,
                    choices=[n for n, _, _ in FAMILIES],
                    help="run a single family of checks")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="emit findings as JSON")
    ap.add_argument("--external", action="append", default=[],
                    metavar="NAME=PATH",
                    help="register a document that specs may cite by name, so "
                         "`NAME §n.n` resolves against it instead of locally. "
                         f"Defaults: {', '.join(EXTERNAL_SPECS)}")
    args = ap.parse_args()

    specs = args.specs or [Path(p) for p in DEFAULT_SPECS]

    # Resolve the external registry once; every spec checked shares it.
    external_paths = dict(EXTERNAL_SPECS)
    for item in args.external:
        if "=" not in item:
            print(f"spec_check: --external expects NAME=PATH, got {item!r}",
                  file=sys.stderr)
            return 2
        name, _, path = item.partition("=")
        external_paths[name.strip()] = path.strip()

    externals: dict[str, set[str]] = {}
    for name, path in external_paths.items():
        p = Path(path)
        if not p.exists():
            # Registered but unreadable is worse than unregistered: every
            # citation of it would silently resolve locally. Fail instead.
            print(f"spec_check: external {name} -> {p} does not exist",
                  file=sys.stderr)
            return 2
        externals[name] = {h.number for h in Spec(p.read_text(encoding="utf-8")).headings}

    reports = []
    for path in specs:
        if not path.exists():
            print(f"spec_check: {path} does not exist", file=sys.stderr)
            return 2
        try:
            spec = Spec(path.read_text(encoding="utf-8"), externals)
        except OSError as exc:
            print(f"spec_check: could not read {path}: {exc}", file=sys.stderr)
            return 2
        reports.append((path, spec, run(spec, args.only)))

    findings = [f for _, _, res in reports for _, _, _, fs in res for f in fs]
    errors = [f for f in findings if f.level == ERROR]
    warnings = [f for f in findings if f.level == WARNING]

    if args.as_json:
        print(json.dumps({
            "specs": [
                {
                    "spec": str(path),
                    "headings": len(spec.headings),
                    "definitions": len(spec.definitions),
                    "families": [
                        {
                            "family": name, "status": status,
                            "findings": [
                                {"level": f.level, "line": f.line,
                                 "message": f.message} for f in fs
                            ],
                        }
                        for name, _, status, fs in res
                    ],
                }
                for path, spec, res in reports
            ],
            "errors": len(errors),
            "warnings": len(warnings),
        }, indent=2))
    else:
        for path, spec, res in reports:
            print(f"\n{path}")
            print(f"  {len(spec.headings)} numbered headings, "
                  f"{len(spec.definitions)} requirement definitions")
            for name, title, status, fs in res:
                if status == "n/a":
                    print(f"  [n/a    ] {name:11}  {title} — document defines "
                          f"no identifiers, nothing to check")
                    continue
                label = "clean" if not fs else f"{len(fs)} finding(s)"
                print(f"  [checked] {name:11}  {title} — {label}")
                for f in sorted(fs, key=lambda x: (x.level != ERROR, x.line)):
                    print(f.render(str(path)))
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        if warnings and not args.strict:
            print("warnings do not fail the build; use --strict to promote them")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
