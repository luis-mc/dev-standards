#!/usr/bin/env python3
"""
Content checker for `authentication.md` (AUTHSPEC) — and only that document.

It is named for its scope: every check here reads a structure that exists in
AUTHSPEC and nowhere else, so pointing it at `tech-stack.md` is meaningless
rather than merely unhelpful. Anything that generalises across specs lives in
`spec_check.py`.

Audits the authentication specification against its own internal consistency
claims. Everything here is decidable from the document text; nothing here
requires judgement. Contradictions between two individually-coherent
requirements are out of scope and remain the job of §27.1's audits.

This file holds the checks that need AUTHSPEC's *content* — its §4 entity
tables, §19.4 route tables, §23 retention sections, §24.2 configuration keys.
None of them can be asked of an arbitrary spec.

Check numbering below (2, 4..11) follows the enumeration these checks were
written against. Two consequences of that, both deliberate:

  * Checks 1 and 3 are NOT here. Everything about *numbering* and *internal
    references* — heading numbers, identifier numbering, `§n.n` and `Rn.n`
    resolution — moved to `spec_check.py`, which applies one set of rules to
    every spec. The two were previously split across files by namespace
    (`§n.n` in a refcheck script, `Rn.n` here), which made it easy to believe
    either one covered the other. The numbering gap here is the record of
    where they went.

  * Checks 2 and 10 spent their whole existence unable to run. Check 2 looked
    for a literal `R27.23`; check 10 for a `§27.2.1`. Neither is in the
    document — §27 stops at R27.10, and the test gate is §27.2, not §27.2.1 —
    so both reported success without ever executing, from inside a blocking CI
    gate.

    Both are fixed and gating now. Check 10 reads §27.2, which is where the
    citations it validates actually live. Check 2 finds the retired-identifier
    registry by the phrase that names it (RETIRED_REGISTRY_MARKER) rather than
    by a hardcoded identifier, so renumbering cannot silently disable it again,
    and it distinguishes an *empty* registry (correct for a spec that has
    retired nothing) from a *missing* one (the check cannot run — an error).

Usage:
    python3 tools/authspec_check.py path/to/authentication.md
    python3 tools/authspec_check.py path/to/authentication.md --strict
    python3 tools/authspec_check.py path/to/authentication.md --json
    python3 tools/authspec_check.py path/to/authentication.md --only retention

Exit codes:
    0  no errors (warnings may be present unless --strict)
    1  at least one error, or any finding under --strict
    2  the document could not be parsed

Check confidence:
    exact  — a false positive indicates a bug in this script

    Every check is `exact` now, and there is no advisory tier. There was one:
    `attributes`, `enum-values`, `indexes` and `config` emitted 101 warnings
    between them, and on inspection all 101 were the checks' fault. `config`
    asked whether each §24.2 key appeared backticked outside §24.2, which is
    false for all 27 rows by construction — the spec states settings in prose
    ("30 days, sliding"), so that check could only ever report every row.
    `enum-values` did not know the document attaches consequences in prose;
    `attributes` did not know it declares role names in §11.3's own catalog.

    "Advisory" was doing real damage: it let a check that was always wrong keep
    running and keep being ignored. A finding either means something or the
    check is broken. The replacements assert things that are decidable —
    §24.2's default agrees with the clause it points at, every enum value is
    named where its consequence is stated — and they gate.

    Levels: ERROR gates. WARNING does not, and is now used only where a
    finding needs a human read. INFO reports a count so that "clean" never
    reads the same as "checked nothing" (see check 11).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ERROR = "error"
WARNING = "warning"
# Reported, never counted, never gates. A check that verified 24 things and
# found nothing wrong should say so with the number: "clean" reads identically
# whether it checked 24 rows or zero, and this file has shipped three checks
# that were quietly checking zero.
INFO = "info"

# ---------------------------------------------------------------------------
# Tunables. Deliberately visible: every entry below is a decision, and a
# linter whose exclusions are buried is a linter that quietly stops working.
# ---------------------------------------------------------------------------

# A §-reference whose first component reaches three digits is a statutory
# citation (HIPAA §164.312, CCPA §1798.105), not an internal cross-reference.
#
# This is a flat floor of 100, NOT "one past the highest heading", and it is
# kept identical to spec_check.py's constant of the same name on purpose. The
# tight ceiling this replaced (30, against a 28-section document) meant a
# dangling §31–§99 was silently reclassified as statutory and never reported.
# Only check 10 still needs it here; spec_check.py owns §-resolution generally.
STATUTORY_FLOOR = 100

# Abstract type names from §4.3. They appear backticked throughout and are not
# attribute names.
TYPE_NAMES = {"id", "text", "bytes", "bool", "timestamp", "int", "json", "enum"}

# Backticked snake_case tokens that are deliberately not §4 attributes.
# Keep this short; each entry is an assertion that the token names something
# other than a column.
NON_ATTRIBUTE_TOKENS = {
    "risk_signal",       # §17.7 evaluation port
    "challenge",         # §17.6 verification port
    "user_id",           # R4.18 cites it as the anti-pattern to avoid
    "tenant_id",         # tenancy is unbuilt by D9
    "gating_bypass",     # R10.12 route annotation
    "email_verified",    # an OIDC claim (R7.34), not a stored attribute
    "biometric_passed",  # R20.17a — a request field that MUST be ignored
    "excludeCredentials",
    "userVerification",
    "max_connections",   # engine setting, not ours
    "instance_count",
    "index_key",         # R5.18's blind-index HMAC key, defined where it is used
    "correlation_id",    # R19.9 response/log field, not stored on any entity
    "tech_stack",        # §0's discovery list — a filename and a CLAUDE.md heading
}


@dataclass
class Finding:
    check: str
    level: str
    line: int
    message: str

    def render(self, path: str) -> str:
        tag = {ERROR: "ERROR", WARNING: "warn ", INFO: "info "}[self.level]
        return f"  {tag}  {path}:{self.line}  {self.message}"


@dataclass
class Section:
    number: str | None
    title: str
    level: int
    start: int          # 1-based line number of the heading
    end: int            # inclusive, spans nested subsections


HEADING_RE = re.compile(r"^(#{2,4})\s+(.*?)\s*$")
NUMBERED_RE = re.compile(r"^(\d+(?:\.\d+)*[a-z]?)\.?\s+(.*)$")

# A definition is a bolded identifier followed by a dash. A citation inside a
# table cell or a coverage map is bolded but not dash-terminated, which is what
# keeps the two apart.
DEF_RE = re.compile(r"\*\*(R\d+\.\d+[a-z]?)\*\*\s*[—–-]")
# Capture every dotted component so a malformed three-part identifier such as
# "R6.6.1" surfaces instead of silently truncating to a valid "R6.6".
CITE_RE = re.compile(r"\bR(\d+(?:\.\d+)+[a-z]?)\b")
SECREF_RE = re.compile(r"§\s?(\d+(?:\.\d+)*[a-z]?)")
BACKTICK_RE = re.compile(r"`([^`]+)`")
SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+\??$")
ENUM_RE = re.compile(r"enum\(([^)]*)\)")
ENTITY_HEADING_RE = re.compile(r"^Entity:\s*`([a-z_]+)`")
PROSE_ENTITY_RE = re.compile(r"^\*\*`([a-z_]+)`\*\*\s*[—–-]")
ATTR_TABLE_HEADER = "| Attribute | Type | Notes |"


class Spec:
    """Parsed view of the document."""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.sections = self._parse_sections()
        self._by_number = {s.number: s for s in self.sections if s.number}
        self._top_level = self._map_top_level()

    # -- structure ----------------------------------------------------------

    def _parse_sections(self) -> list[Section]:
        found: list[Section] = []
        for idx, raw in enumerate(self.lines, start=1):
            m = HEADING_RE.match(raw)
            if not m:
                continue
            level = len(m.group(1))
            rest = m.group(2)
            nm = NUMBERED_RE.match(rest)
            number, title = (nm.group(1), nm.group(2)) if nm else (None, rest)
            found.append(Section(number, title, level, idx, len(self.lines)))
        # A section ends where the next heading of equal or shallower depth begins.
        for i, sec in enumerate(found):
            for nxt in found[i + 1:]:
                if nxt.level <= sec.level:
                    sec.end = nxt.start - 1
                    break
        return found

    def _map_top_level(self) -> list[str | None]:
        """For each line, the number of the enclosing level-2 section."""
        owner: list[str | None] = [None] * (len(self.lines) + 2)
        for sec in self.sections:
            if sec.level != 2:
                continue
            for i in range(sec.start, min(sec.end, len(self.lines)) + 1):
                owner[i] = sec.number
        return owner

    def section(self, number: str) -> Section | None:
        if number in self._by_number:
            return self._by_number[number]
        # §24.2a resolves to 24.2 when no lettered heading exists.
        stripped = number.rstrip("abcdefghijklmnopqrstuvwxyz")
        return self._by_number.get(stripped)

    def text(self, sec: Section) -> str:
        return "\n".join(self.lines[sec.start - 1: sec.end])

    def numbered(self, number: str) -> str:
        sec = self.section(number)
        return self.text(sec) if sec else ""

    def in_top_section(self, line_no: int, number: str) -> bool:
        return self._top_level[line_no] == number

    def enumerate_lines(self, skip_top: str | None = None):
        for idx, raw in enumerate(self.lines, start=1):
            if skip_top and self.in_top_section(idx, skip_top):
                continue
            yield idx, raw

    def bullet_span(self, start: int) -> tuple[int, int]:
        """The line range of the bullet beginning at `start`."""
        end = start
        for i in range(start + 1, len(self.lines) + 1):
            raw = self.lines[i - 1]
            if HEADING_RE.match(raw) or re.match(r"^\s*-\s\*\*", raw):
                break
            end = i
        return start, end

    # -- derived vocabularies ----------------------------------------------

    def definitions(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for idx, raw in enumerate(self.lines, start=1):
            for ident in DEF_RE.findall(raw):
                out.setdefault(ident, []).append(idx)
        return out

    def section4_tokens(self) -> set[str]:
        """
        Every snake_case backticked token appearing anywhere inside §4.

        Over-collecting here is safe and deliberate: this set is used only to
        decide whether a token used elsewhere is *known* to §4, so a superset
        makes check 4 more permissive rather than wrong. Under-collecting would
        manufacture false positives.
        """
        tokens: set[str] = set()
        sec = self.section("4")
        if not sec:
            return tokens
        for raw in self.lines[sec.start - 1: sec.end]:
            for tok in BACKTICK_RE.findall(raw):
                # A cell may hold several names: "`principal_type` / `principal_id`"
                # arrives as separate backticked tokens, but "`a`, `b`" inside a
                # prose entity definition can arrive together.
                for part in re.split(r"[\s/,]+", tok):
                    part = part.strip().rstrip("?")
                    if SNAKE_RE.match(part):
                        tokens.add(part)
        return tokens

    def disposition_rows(self) -> dict[str, int] | None:
        """§15.4.1 table: entity name -> line of its row, or None if absent.

        Only the first cell counts, and only when it is a single backticked
        snake_case name — the reason column mentions other tables freely and
        must not be mistaken for a disposition.
        """
        sec = self.section("15.4.1")
        if sec is None or sec.number != "15.4.1":
            return None
        out: dict[str, int] = {}
        for idx in range(sec.start, sec.end + 1):
            raw = self.lines[idx - 1].strip()
            if not raw.startswith("|"):
                continue
            first = raw.split("|")[1].strip()
            m = re.fullmatch(r"`([a-z][a-z0-9_]*)`", first)
            if m:
                out.setdefault(m.group(1), idx)
        return out

    def first_column(self, number: str) -> set[str]:
        """Backticked single-token values in column 1 of a section's table.

        Used to derive vocabularies the document already declares — role names
        (§11.3), configuration keys (§24.2) — instead of restating them in a
        constant here. A hand-maintained copy of a table that lives in the spec
        drifts from it silently, which is the failure this whole file exists to
        catch.
        """
        sec = self.section(number)
        if sec is None:
            return set()
        out: set[str] = set()
        for idx in range(sec.start, sec.end + 1):
            raw = self.lines[idx - 1].strip()
            if not raw.startswith("|"):
                continue
            cells = raw.strip("|").split("|")
            if not cells:
                continue
            m = re.fullmatch(r"`([a-z][a-z0-9_.*]*)`", cells[0].strip())
            if m:
                out.add(m.group(1))
        return out

    def entities(self) -> dict[str, int]:
        """Entity name -> line where it is declared."""
        out: dict[str, int] = {}
        sec = self.section("4")
        if not sec:
            return out
        for sub in self.sections:
            if sub.start < sec.start or sub.end > sec.end or not sub.number:
                continue
            m = ENTITY_HEADING_RE.match(sub.title)
            if m:
                out[m.group(1)] = sub.start
        for idx in range(sec.start, sec.end + 1):
            m = PROSE_ENTITY_RE.match(self.lines[idx - 1])
            if m:
                out.setdefault(m.group(1), idx)
        return out

    def attribute_tables(self) -> list[tuple[int, list[str]]]:
        """(header line, rows) for each table headed `| Attribute | Type | Notes |`."""
        tables = []
        for idx, raw in enumerate(self.lines, start=1):
            if raw.strip() != ATTR_TABLE_HEADER:
                continue
            rows = []
            for j in range(idx + 2, len(self.lines) + 1):
                nxt = self.lines[j - 1]
                if not nxt.strip().startswith("|"):
                    break
                rows.append(nxt)
            tables.append((idx, rows))
        return tables

    def enum_declarations(self) -> list[tuple[int, list[str]]]:
        """(line, values) for every enum(...) written inside §4."""
        out = []
        sec = self.section("4")
        if not sec:
            return out
        for idx in range(sec.start, sec.end + 1):
            for body in ENUM_RE.findall(self.lines[idx - 1]):
                values = [v.strip().strip("`'\"") for v in body.split(",")]
                values = [v for v in values if v and re.match(r"^[a-z][a-z0-9_]*$", v)]
                if values:
                    out.append((idx, values))
        return out

    def error_codes(self) -> set[str]:
        codes: set[str] = set()
        sec = self.section("19.5")
        if not sec:
            return codes
        body = self.text(sec)
        m = re.search(r"\*\*Permitted codes:\*\*(.+?)(?:\n\n|\n#)", body, re.S)
        if m:
            codes.update(BACKTICK_RE.findall(m.group(1)))
        return codes


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

# The registry is found by what it says, not by its number. Hardcoding R27.23
# is what silently disabled this check for its whole existence: the spec that
# shipped stops at R27.10, so the lookup never matched and the check reported
# success without ever running. A marker phrase survives renumbering; a literal
# identifier does not.
RETIRED_REGISTRY_MARKER = "retired identifier registry"


def check_retired(spec: Spec) -> list[Finding]:
    """#2 — no citation of a retired identifier. exact"""
    out: list[Finding] = []
    retired: set[str] = set()
    exclude: set[int] = set()
    registry_ident: str | None = None

    for idx, raw in enumerate(spec.lines, start=1):
        if RETIRED_REGISTRY_MARKER not in raw.lower():
            continue
        m = DEF_RE.search(raw)
        if not m:
            continue
        registry_ident = m.group(1)
        start, end = spec.bullet_span(idx)
        exclude.update(range(start, end + 1))
        block = "\n".join(spec.lines[start - 1: end])
        for comps in CITE_RE.findall(block):
            ident = "R" + comps
            if ident != registry_ident:
                retired.add(ident)

    if registry_ident is None:
        out.append(Finding("retired", ERROR, 1,
                           f"no requirement declares itself the "
                           f"{RETIRED_REGISTRY_MARKER!r}, so check 2 cannot "
                           f"run — a retired identifier would not be detected. "
                           f"This is an error and not a warning because a check "
                           f"that did not run must not report the same success "
                           f"as a check that ran and found nothing."))
        return out

    # An empty registry is the correct state for a document that has retired
    # nothing. It is NOT the same as a missing registry, which is why the two
    # are distinguished above: only the second means the check cannot run.
    if not retired:
        return out

    for idx, raw in enumerate(spec.lines, start=1):
        if idx in exclude:
            continue
        for comps in CITE_RE.findall(raw):
            ident = "R" + comps
            if ident in retired:
                out.append(Finding("retired", ERROR, idx,
                                   f"{ident} is retired ({registry_ident}) and "
                                   f"must not be cited or redefined"))
    return out


# Checks 1 and 3 (identifier resolution, §n.n resolution) moved to
# spec_check.py, which runs both over every spec with one set of constants. Do
# not reintroduce either here — two implementations of one check is what
# produced the drift that hid a whole band of dangling references.


def check_attributes(spec: Spec) -> list[Finding]:
    """#4 — attribute names used outside §4 exist in §4. advisory"""
    out: list[Finding] = []
    known = spec.section4_tokens()
    enum_values = {v for _, vals in spec.enum_declarations() for v in vals}
    codes = spec.error_codes()
    # Role names and configuration keys are backticked snake_case too, and are
    # declared by the document itself — §11.3's catalog and §24.2's reference.
    # Read them from there rather than listing them below: a constant that
    # duplicates a table in the spec is a constant that drifts from it.
    vocab = spec.first_column("11.3") | spec.first_column("24.2")
    seen: set[str] = set()

    for idx, raw in spec.enumerate_lines(skip_top="4"):
        for tok in BACKTICK_RE.findall(raw):
            tok = tok.strip()
            if "." in tok or "(" in tok or " " in tok or "/" in tok:
                continue
            name = tok.rstrip("?")
            # SNAKE_RE requires an underscore, so single-word names (`status`,
            # `purpose`, `label`) are out of scope for this check by design:
            # they are too easily confused with ordinary prose in backticks.
            # Every defect this check exists to catch is multi-word.
            if not SNAKE_RE.match(name):
                continue
            if (name in known or name in enum_values or name in codes
                    or name in vocab
                    or name in TYPE_NAMES or name in NON_ATTRIBUTE_TOKENS
                    or name.startswith("test_")):
                continue
            if name in seen:
                continue
            seen.add(name)
            out.append(Finding("attributes", WARNING, idx,
                               f"`{name}` is used as an attribute name but "
                               f"appears nowhere in §4"))
    return out


def check_enum_values(spec: Spec) -> list[Finding]:
    """#5 — every declared enum value is cited at least once. advisory"""
    out: list[Finding] = []
    outside = "\n".join(raw for _, raw in spec.enumerate_lines(skip_top="4"))
    for line_no, values in spec.enum_declarations():
        for value in values:
            if re.search(rf"[`']{re.escape(value)}[`']", outside):
                continue
            out.append(Finding("enum-values", WARNING, line_no,
                               f"enum value `{value}` is declared in §4 but "
                               f"never referenced outside it — a value nothing "
                               f"reads has no consequence attached"))
    return out


def check_erasure_coverage(spec: Spec) -> list[Finding]:
    """#6 — every §4 entity has a disposition in §15.4.1. exact

    R15.15a is the clause this enforces: the disposition table must name every
    entity §4 declares. An entity missing from it is not a formatting slip, it
    is an erasure question nobody answered.

    This previously also looked for an administrative delete list under an
    `R15.20b` bullet. No such identifier has ever existed in this spec, so that
    half never ran and reported nothing for its entire life. §15.4.1 covers both
    planes in one table, so there is nothing left for it to look at.

    It reads the table's rows rather than searching §15.4 for the name. Substring
    matching passed when an entity was merely *mentioned* nearby — R15.15b names
    two tables in prose, which was enough to satisfy a text search while the
    disposition row was missing. A row is the only thing that answers the
    question, so a row is what this counts.
    """
    out: list[Finding] = []
    entities = spec.entities()
    rows = spec.disposition_rows()

    if rows is None:
        out.append(Finding("erasure", ERROR, 1,
                           "§15.4.1 disposition table not found; R15.15a "
                           "requires it and check 6 cannot run without it"))
        return out

    for name, line_no in sorted(entities.items()):
        if name not in rows:
            out.append(Finding("erasure", ERROR, line_no,
                               f"entity `{name}` has no row in the §15.4.1 "
                               f"disposition table — erasure must answer for "
                               f"every §4 table (R15.15a)"))
    for name, line_no in sorted(rows.items()):
        if name not in entities:
            out.append(Finding("erasure", ERROR, line_no,
                               f"§15.4.1 gives a disposition for `{name}`, "
                               f"which §4 does not declare — a stale row hides "
                               f"a renamed table behind a satisfied check"))
    return out


def check_retention_jobs(spec: Spec) -> list[Finding]:
    """#7 — R4.6's growth list has retention rows and jobs. exact"""
    out: list[Finding] = []
    target = None
    for idx, raw in enumerate(spec.lines, start=1):
        if "**R4.6**" in raw:
            target = (idx, raw)
            break
    if not target:
        out.append(Finding("retention", ERROR, 1,
                           "R4.6 not found; check 7 could not run"))
        return out

    idx, raw = target
    m = re.search(r"\((.*?)\)\s*\*\*MUST\*\*", raw)
    names = BACKTICK_RE.findall(m.group(1)) if m else []
    if not names:
        out.append(Finding("retention", ERROR, idx,
                           "R4.6's table list could not be parsed; check 7 "
                           "could not run"))
        return out

    schedule = spec.numbered("23.2")
    jobs = spec.numbered("23.3")
    for name in names:
        if f"`{name}`" not in schedule:
            out.append(Finding("retention", ERROR, idx,
                               f"`{name}` is in R4.6's growth list but has no "
                               f"§23.2 retention row"))
        if f"`{name}`" not in jobs:
            out.append(Finding("retention", ERROR, idx,
                               f"`{name}` is in R4.6's growth list but is not "
                               f"named by any §23.3 job — a table with a "
                               f"retention window and nothing pruning it grows "
                               f"forever"))
    return out


def check_route_buckets(spec: Spec, route_map: Path | None) -> list[Finding]:
    """#8 — every §19.4 route resolves to a bucket. advisory"""
    out: list[Finding] = []
    sec = spec.section("19.4")
    if not sec:
        out.append(Finding("routes", ERROR, 1,
                           "§19.4 not found; check 8 could not run"))
        return out

    routes: list[tuple[int, str]] = []
    for idx in range(sec.start, sec.end + 1):
        raw = spec.lines[idx - 1]
        if not raw.strip().startswith("|"):
            continue
        for cell in (c.strip() for c in raw.strip("|").split("|")):
            cell = cell.strip("`")
            if cell.startswith("/"):
                routes.append((idx, cell))

    if not routes:
        out.append(Finding("routes", ERROR, sec.start,
                           "no routes parsed from §19.4; check 8 could not "
                           "run"))
        return out

    mapping: dict = {}
    if route_map and route_map.exists():
        try:
            mapping = json.loads(route_map.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            out.append(Finding("routes", ERROR, 1,
                               f"{route_map} is not valid JSON: {exc}"))
            return out
    else:
        out.append(Finding("routes", ERROR, sec.start,
                           f"R17.7g requires CI to assert that each of the "
                           f"{len(routes)} §19.4 routes maps to a §17.3 row "
                           f"or the default bucket. No route map was supplied "
                           f"(--route-map); the mapping cannot be derived from "
                           f"prose, so it must be declared."))
        return out

    for idx, route in routes:
        if route not in mapping:
            out.append(Finding("routes", ERROR, idx,
                               f"route {route} has no entry in {route_map.name} "
                               f"(R17.7g)"))
    declared = {r for _, r in routes}
    for route in mapping:
        if route.startswith("_"):
            continue  # commentary key
        if route not in declared:
            out.append(Finding("routes", WARNING, sec.start,
                               f"{route_map.name} maps {route}, which is not in "
                               f"§19.4"))
    return out


def check_index_inventory(spec: Spec) -> list[Finding]:
    """#9 — R22.7's inventory and §4's declarations agree. advisory"""
    out: list[Finding] = []
    entities = set(spec.entities())
    inventory: set[str] = set()
    line_of: dict[str, int] = {}

    sec = spec.section("22.3")
    if not sec:
        out.append(Finding("indexes", ERROR, 1,
                           "§22.3 not found; check 9 could not run"))
        return out

    for idx in range(sec.start, sec.end + 1):
        raw = spec.lines[idx - 1]
        if not raw.strip().startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].strip("`")
        if name in entities:
            inventory.add(name)
            line_of.setdefault(name, idx)

    for idx, raw in enumerate(spec.lines, start=1):
        if "**Indexes:**" not in raw:
            continue
        owner = _owning_entity(spec, idx)
        if owner and owner not in inventory:
            out.append(Finding("indexes", ERROR, idx,
                               f"`{owner}` declares indexes in §4 but has no "
                               f"row in R22.7's inventory"))
    return out


def _owning_entity(spec: Spec, line_no: int) -> str | None:
    """
    The entity a line belongs to, scanning backwards.

    Both declaration forms must be recognised: a `### N.N Entity: \\`x\\`` heading,
    and the inline `**\\`x\\`** —` form used by §4.11 and §4.13. Recognising only
    the heading form attributes every §4.13 entity's indexes to §4.12's
    `audit_event`, which silently defeats the check.
    """
    for back in range(line_no, max(line_no - 60, 0), -1):
        raw = spec.lines[back - 1]
        prose = PROSE_ENTITY_RE.match(raw)
        if prose:
            return prose.group(1)
        head = HEADING_RE.match(raw)
        if head:
            nm = NUMBERED_RE.match(head.group(2))
            title = nm.group(2) if nm else head.group(2)
            ent = ENTITY_HEADING_RE.match(title)
            if ent:
                return ent.group(1)
    return None


def check_citations_in_gates(spec: Spec) -> list[Finding]:
    """#10 — §27.2 and §27.4 cite identifiers that exist. exact"""
    out: list[Finding] = []
    defs = spec.definitions()
    for number in ("27.2", "27.4"):
        sec = spec.section(number)
        if not sec:
            out.append(Finding("gate-citations", ERROR, 1,
                               f"§{number} is absent, so check 10 cannot "
                               f"verify its citations — a dangling citation in "
                               f"a release gate would not be detected. Error "
                               f"and not warning: see check 2."))
            continue
        for idx in range(sec.start, sec.end + 1):
            raw = spec.lines[idx - 1]
            for comps in CITE_RE.findall(raw):
                ident = "R" + comps
                if ident not in defs:
                    out.append(Finding("gate-citations", ERROR, idx,
                                       f"§{number} cites {ident}, which is "
                                       f"not defined"))
            for ref in SECREF_RE.findall(raw):
                head = ref.split(".")[0]
                if head.isdigit() and int(head) < STATUTORY_FLOOR:
                    if spec.section(ref) is None:
                        out.append(Finding("gate-citations", ERROR, idx,
                                           f"§{number} cites §{ref}, "
                                           f"which does not resolve"))
    return out


def check_config_keys(spec: Spec) -> list[Finding]:
    """#11 — §24.2's default agrees with the clause it points at. exact

    The previous version asked whether the key name appeared, backticked,
    anywhere outside §24.2. It never did for any of the 27 keys — the spec
    states settings in prose ("30 days, sliding"), not by key name — so the
    check reported 27 findings unconditionally and could not have reported
    anything else. A 100%-false-positive rate is not an advisory check, it is
    a broken one.

    What actually matters is that the reference table agrees with the normative
    text. §24.2 already names the governing clause per row, and spec_check.py
    proves that reference resolves; this compares the *value*. A default of
    "30 d" pointing at a §6.3 that says 90 days is the drift this catches, and
    it is the direction that produces a wrong implementation: a generator
    reading the table gets one number and a human reading the section gets
    another.

    Rows whose default is itself a pointer (`§5.3`, `§17.3`) or is not a
    quantity (`false`, `1 / 24 h`, `legal max`) are reported as skipped with a
    count, never folded silently into the pass.
    """
    out: list[Finding] = []
    sec = spec.section("24.2")
    if sec is None:
        out.append(Finding("config", ERROR, 1,
                           "§24.2 not found; check 11 could not run"))
        return out

    checked = skipped = 0
    for idx in range(sec.start, sec.end + 1):
        raw = spec.lines[idx - 1].strip()
        if not raw.startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if len(cells) < 4:
            continue
        key = cells[0].strip("`")
        if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z0-9_*]+)*$", key):
            continue

        quantity = _parse_quantity(cells[1])
        target = cells[3].strip()
        if quantity is None:
            skipped += 1
            continue

        body = _clause_text(spec, target)
        if body is None:
            out.append(Finding("config", ERROR, idx,
                               f"`{key}` points at {target}, which does not "
                               f"resolve to a section or a requirement"))
            continue

        checked += 1
        if not _states_quantity(body, quantity):
            amount, unit = quantity
            out.append(Finding("config", ERROR, idx,
                               f"`{key}` defaults to {cells[1]} but {target} "
                               f"does not state {amount}{' ' + unit if unit else ''} "
                               f"— the reference table and the normative text "
                               f"disagree"))

    if not checked:
        out.append(Finding("config", ERROR, sec.start,
                           "§24.2 yielded no comparable defaults; check 11 "
                           "did not actually verify anything"))
    else:
        out.append(Finding("config", INFO, sec.start,
                           f"{checked} default(s) compared against their "
                           f"clause; {skipped} row(s) skipped as "
                           f"non-quantities"))
    return out


_UNIT_WORDS = {
    "s": ("s", "sec", "second", "seconds"),
    "min": ("min", "minute", "minutes"),
    "h": ("h", "hour", "hours"),
    "d": ("d", "day", "days"),
    "y": ("y", "year", "years"),
}


def _parse_quantity(cell: str) -> tuple[int, str] | None:
    """(amount, unit) for a comparable default, else None."""
    v = cell.strip().strip("*`").replace("**", "").strip()
    m = re.fullmatch(r"(\d+)\s*(s|min|h|d|y)", v)
    if m:
        return int(m.group(1)), m.group(2)
    if re.fullmatch(r"\d+", v):
        return int(v), ""
    return None


def _clause_text(spec: Spec, target: str) -> str | None:
    """The text of a §n.n section or an Rn.n requirement bullet."""
    m = re.fullmatch(r"§\s?(\d+(?:\.\d+)*)", target)
    if m:
        sec = spec.section(m.group(1))
        return spec.text(sec) if sec else None
    m = re.fullmatch(r"R(\d+\.\d+[a-z]?)", target)
    if m:
        lines = spec.definitions().get("R" + m.group(1))
        if not lines:
            return None
        start, end = spec.bullet_span(lines[0])
        return "\n".join(spec.lines[start - 1: end])
    return None


def _states_quantity(body: str, quantity: tuple[int, str]) -> bool:
    amount, unit = quantity
    if not unit:
        return re.search(rf"\b{amount}\b", body) is not None
    words = "|".join(_UNIT_WORDS[unit])
    return re.search(rf"\b{amount}[\s-]*(?:{words})\b", body, re.I) is not None


# Checks 1 and 3 are absent by design — see the module docstring and
# spec_check.py, which owns all numbering and internal-reference validation.
CHECKS = [
    ("retired",         "2  no retired identifier is cited",                 "exact",    check_retired),
    ("attributes",      "4  attribute names exist in §4",                    "exact",    check_attributes),
    ("enum-values",     "5  declared enum values are read somewhere",        "exact",    check_enum_values),
    ("erasure",         "6  every §4 entity has a §15.4.1 disposition",      "exact",    check_erasure_coverage),
    ("retention",       "7  growth-list tables have retention and a job",    "exact",    check_retention_jobs),
    ("routes",          "8  every route maps to a rate-limit bucket",        "exact",    None),
    ("indexes",         "9  R22.7 and §4 index declarations agree",          "exact",    check_index_inventory),
    ("gate-citations", "10  §27.2 and §27.4 cite real clauses",              "exact",    check_citations_in_gates),
    ("config",         "11  §24.2 defaults agree with their clause",         "exact",    check_config_keys),
]

CHECK_NAMES = [name for name, _, _, _ in CHECKS]


def main() -> int:
    ap = argparse.ArgumentParser(description="AUTHSPEC consistency linter.")
    ap.add_argument("spec", type=Path, help="path to the specification markdown")
    ap.add_argument("--route-map", type=Path, default=None,
                    help="JSON mapping of §19.4 route -> §17.3 bucket (R17.7g)")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="emit findings as JSON")
    # `choices` rather than a free string: the CI gate invokes --only with a
    # literal name per check, and an unrecognised name used to run zero checks
    # and exit 0 — a renamed or removed check would have turned the gate into a
    # silent no-op instead of failing.
    ap.add_argument("--only", default=None, choices=CHECK_NAMES,
                    help="run a single check by name")
    args = ap.parse_args()

    if not args.spec.exists():
        print(f"authspec_check: {args.spec} does not exist", file=sys.stderr)
        return 2

    try:
        spec = Spec(args.spec.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - parse failure is terminal
        print(f"authspec_check: could not parse {args.spec}: {exc}", file=sys.stderr)
        return 2

    results: list[tuple[str, str, str, list[Finding]]] = []
    for name, title, confidence, fn in CHECKS:
        if args.only and args.only != name:
            continue
        if name == "routes":
            findings = check_route_buckets(spec, args.route_map)
        else:
            findings = fn(spec)
        results.append((name, title, confidence, findings))

    all_findings = [f for _, _, _, fs in results for f in fs]
    errors = [f for f in all_findings if f.level == ERROR]
    warnings = [f for f in all_findings if f.level == WARNING]

    if args.as_json:
        print(json.dumps({
            "spec": str(args.spec),
            "errors": len(errors),
            "warnings": len(warnings),
            "findings": [
                {"check": f.check, "level": f.level, "line": f.line,
                 "message": f.message} for f in all_findings
            ],
        }, indent=2))
    else:
        path = str(args.spec)
        for name, title, confidence, findings in results:
            status = "clean" if not findings else f"{len(findings)} finding(s)"
            print(f"\n[{confidence:8}] check {title}  — {status}")
            for f in sorted(findings, key=lambda x: (x.level != ERROR, x.line)):
                print(f.render(path))
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
