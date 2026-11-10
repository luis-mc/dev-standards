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
import importlib.util, sys, pathlib

# Console output carries non-ASCII (em dashes); a Windows console defaults to
# cp1252 and would raise on them. Reconfigure rather than require PYTHONUTF8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

TOOLS = pathlib.Path(__file__).resolve().parent


def load_spec_check():
    """Import the spec-check plugin asset."""
    target = TOOLS.parent / "claude/plugins/docs/skills/spec-check/assets/spec_check.py"
    spec = importlib.util.spec_from_file_location("spec_check", target)
    module = importlib.util.module_from_spec(spec)
    sys.modules["spec_check"] = module
    spec.loader.exec_module(module)
    return module


SC = load_spec_check()

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

    # DS186: F33 lettered outbound citation falls back like an internal one.
    ("F33 lettered outbound resolves",
     BASE + "\nPer OTHERSPEC §5.1a here.\n", None, {"OTHERSPEC": {"5.1"}}),
    # DS186: F34 the second number of a list is checked against the same document.
    ("F34 list second ref is outbound",
     BASE + "\nSee OTHERSPEC §9, §1 here.\n",
     "OTHERSPEC §1 does not resolve", {"OTHERSPEC": {"9"}}),
    ("F34 doubled mark is outbound",
     BASE + "\nSee OTHERSPEC §§1 here.\n",
     "OTHERSPEC §1 does not resolve", {"OTHERSPEC": {"9"}}),
    # DS186: F39 a heading inside a fence is not a heading.
    ("F39 fenced heading ignored",
     BASE + "\n```markdown\n## 1. Example\n```\n", None),
    # DS186: F40 `<!--` in inline code does not open a comment.
    ("F40 comment marker in code",
     BASE + "\nOpen with `<!--` here.\n\n### 9.1 Orphan\n",
     "has no parent heading 9"),
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

# DS186: command-line cases (F31, F32, F41, F42). Each runs the script from a
# directory that is not the repo root.
import subprocess, tempfile
CLI = TOOLS.parent / "claude/plugins/docs/skills/spec-check/assets/spec_check.py"


def cli(name, files, args, want_code, want_text):
    global fails
    with tempfile.TemporaryDirectory() as d:
        for fname, data in files.items():
            fp = pathlib.Path(d) / fname
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(data)
        r = subprocess.run([sys.executable, str(CLI), *args], cwd=d,
                           capture_output=True, text=True, encoding="utf-8")
    out = r.stdout + r.stderr
    ok = r.returncode == want_code and want_text in out and "Traceback" not in out
    print(f"{'PASS' if ok else 'FAIL'}  {name:36} exit={r.returncode}")
    if not ok:
        print(out)
    fails += not ok


GOOD = "## 1. Intro\n\nSee STACKSPEC §1.\n".encode()
cli("F31 runs outside the repo root", {"t.md": GOOD}, ["t.md"], 0, "0 error(s)")
cli("F32 non-UTF-8 spec exits 2", {"l.md": b"## 1. Intro caf\xe9\n"},
    ["l.md"], 2, "could not read")
cli("F32 non-UTF-8 external exits 2", {"l.md": b"## 1. Intro caf\xe9\n", "a.md": GOOD},
    ["--external", "OTHER=l.md", "a.md"], 2, "could not read")
cli("F41 BOM is ignored", {"b.md": b"\xef\xbb\xbf## 1. Intro\n### 1.1 Sub\nSee \xc2\xa71.\n"},
    ["b.md"], 0, "0 error(s)")
cli("F42 directory expands to *.md", {"s/a.md": GOOD, "s/b.md": GOOD},
    ["s"], 0, "b.md")
cli("explicit missing external is fatal", {"t.md": GOOD},
    ["--external", "NOPE=missing.md", "t.md"], 2, "does not exist")

print(f"\n{len(CASES) - fails}/{len(CASES)} cases behaved as specified")
sys.exit(1 if fails else 0)
