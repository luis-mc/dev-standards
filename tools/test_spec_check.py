#!/usr/bin/env python3
"""Prove every spec_check.py check fires.

Each case is a minimal document containing exactly one defect, plus the
substring the corresponding finding must contain. A check that stops firing —
because a regex drifted, a severity changed, or a branch became unreachable —
fails here instead of going quiet and reporting a clean spec forever. That
failure mode is not hypothetical: two checks in authspec_check.py sat in a blocking
CI gate reporting success for their whole existence because the clauses they
read were absent from the document.

The last two cases are negative: they assert the checker stays silent on things
that only look like defects (statutory citations, lettered insertions).

Run:  python3 tools/test_spec_check.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import spec_check as SC

BASE = """# Doc

## 1. One

- **R1.1** — first.
- **R1.2** — second.

## 2. Two

### 2.1 Sub

- **R2.1** — third.
"""

CASES = [
    ("H1 duplicate heading",
     BASE + "\n## 2. Two again\n\n- **R2.2** — x.\n", "is used 2 times"),
    ("H2 depth mismatch",
     BASE.replace("### 2.1 Sub", "#### 2.1 Sub"), "expected depth 3"),
    ("H3 orphan subsection",
     BASE + "\n### 9.1 Orphan\n\n- **R9.1** — x.\n", "has no parent heading 9"),
    ("H4 sibling gap",
     BASE.replace("## 2. Two", "## 4. Four").replace("### 2.1", "### 4.1")
         .replace("**R2.1**", "**R4.1**"), "gap in top-level"),
    ("H5 out of order",
     "# Doc\n\n## 2. Two\n\n- **R2.1** — a.\n\n## 1. One\n\n- **R1.1** — b.\n",
     "must be in ascending order"),
    ("I1 duplicate definition",
     BASE.replace("- **R1.2** — second.", "- **R1.1** — dupe."),
     "is defined 2 times"),
    ("I2 prefix != section",
     BASE.replace("- **R2.1** — third.", "- **R7.1** — wrong section."),
     "is defined inside §2"),
    ("I3 identifier gap",
     BASE.replace("- **R1.1** — first.\n", ""), "gap in §1 identifier"),
    ("I4 definitions out of order",
     BASE.replace("- **R1.1** — first.\n- **R1.2** — second.",
                  "- **R1.2** — second.\n- **R1.1** — first."),
     "must be in ascending order"),
    ("I5 malformed identifier",
     BASE + "\nSee R6.6.1 for detail.\n", "is malformed"),
    ("X1 dangling section ref",
     BASE + "\nSee §47.2 for detail.\n", "§47.2 does not resolve"),
    ("X2 dangling identifier cite",
     BASE + "\nBound by R99.42.\n", "R99.42 is cited but never defined"),
    ("statutory ref ignored",
     BASE + "\nPer HIPAA §164.312(a).\n", None),
    ("lettered insertion is not a gap",
     BASE.replace("- **R1.2** — second.", "- **R1.1a** — inserted.\n- **R1.2** — second."),
     None),

    # Outbound citations. A conformance document (a product's Stack Profile)
    # is mostly `OTHERSPEC §n.n`, and resolving those against its own headings
    # is how it ends up validated against itself. The collision case below is
    # the one that matters: a local §9 exists, so before this was handled the
    # reference resolved silently to the wrong section and reported clean.
    ("X1b outbound ref resolves",
     BASE + "\nPer OTHERSPEC §5.1 the value is fixed.\n", None, {"OTHERSPEC": {"5.1"}}),
    ("X1b outbound ref dangles",
     BASE + "\nPer OTHERSPEC §5.1 the value is fixed.\n",
     "OTHERSPEC §5.1 does not resolve to a heading in OTHERSPEC", {"OTHERSPEC": {"9.9"}}),
    ("X1b outbound not silently matched to a local heading of the same number",
     BASE + "\nPer OTHERSPEC §1 the value is fixed.\n",
     "OTHERSPEC §1 does not resolve to a heading in OTHERSPEC", {"OTHERSPEC": {"9.9"}}),
    # "MUST NOT contain PII (§16.4)" is an internal reference, not a citation
    # of a document called PII. An unregistered prefix must fall through.
    ("unregistered prefix falls through to internal",
     BASE + "\nMUST NOT contain PII (§1).\n", None),
    ("unregistered prefix that also fails internally is hinted",
     BASE + "\nSee PII §47.2 for detail.\n", "preceded by 'PII'"),
]

fails = 0
for case in CASES:
    name, text, expect = case[0], case[1], case[2]
    externals = case[3] if len(case) > 3 else None
    spec = SC.Spec(text, externals)
    msgs = [f.message for _, _, _, fs in SC.run(spec, None) for f in fs]
    blob = " | ".join(msgs)
    if expect is None:
        ok = not msgs
        detail = "no findings" if ok else f"UNEXPECTED: {blob}"
    else:
        ok = expect in blob
        detail = "fired" if ok else f"DID NOT FIRE (got: {blob or 'nothing'})"
    print(f"{'PASS' if ok else 'FAIL'}  {name:36} {detail}")
    fails += not ok

print(f"\n{len(CASES) - fails}/{len(CASES)} cases behaved as specified")
sys.exit(1 if fails else 0)
