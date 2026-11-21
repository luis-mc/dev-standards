#!/usr/bin/env python3
"""Words lint for the lifecycle contract (DS235a). Language-free: scans WiX .wxl files, .properties and
.strings files, JSON string files and plain `key=value` text files.

LC-2: every lifecycle UI string is a value of the words table in docs/design-system/vN/lifecycle.json, and no
banned word is in it. LC-31: notices are plain: no error code, no HTTP status, no doubled punctuation.

Copy this file to scripts/design/. Edit CONFIG. Run: python3 scripts/design/words_lint.py [--root DIR]
Exit 0 when clean, 1 when a string breaks a rule, 2 on a setup problem. Standard library only.
"""
import json
import re
import sys
from pathlib import Path

CONFIG = {
    "lifecycle_files": ["installer/**/*.wxl", "src/lifecycle/**/*.strings"],  # edit: files that hold lifecycle UI strings
}

DEFAULT_BANNED = ["OK", "Yes", "No", "Install now", "Later", "daemon", "binary", "payload"]
CASE_SENSITIVE = {"OK", "Yes", "No", "Later"}  # the others match in any case


def banned_hits(text, banned=DEFAULT_BANNED):
    out = []
    for w in banned:
        flags = 0 if w in CASE_SENSITIVE else re.I
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text, flags):
            out.append(w)
    return out


PLAIN_RULES = [
    ("error code", r"0x[0-9a-fA-F]|(?<![A-Za-z0-9])[A-Z]{1,5}[-_]?[0-9]{3,}(?![A-Za-z0-9])|\b(?:[Ee]rror|[Cc]ode)\s+[0-9]"),
    ("HTTP status", r"HTTP\s*[1-5][0-9]{2}\b|\bstatus(?:\s+code)?\s+[1-5][0-9]{2}\b"),
    ("doubled punctuation", r"([.,;:!?])\1"),
]


def plain_hits(text):
    return [name for name, rx in PLAIN_RULES if re.search(rx, text, re.I if name == "HTTP status" else 0)]


def table_values(doc):
    vals = set()
    for state in doc.get("words", {}).get("states", {}).values():
        vals.update(v for v in state.values() if isinstance(v, str))
    return vals


def banned_list(doc):
    return list(dict.fromkeys(DEFAULT_BANNED + list(doc.get("words", {}).get("banned", []))))


def _unescape(s):
    import html
    return html.unescape(s).strip()


def literals(path, text):
    """The user-facing strings of one file, by extension."""
    suffix = Path(path).suffix.lower()
    if suffix in (".wxl", ".xml", ".resx"):
        return [_unescape(m) for m in re.findall(r"<(?:String|value)\b[^>]*>([^<]*)</(?:String|value)>", text) if m.strip()]
    if suffix == ".json":
        found = []
        def walk(x):
            if isinstance(x, str): found.append(x)
            elif isinstance(x, dict): [walk(v) for v in x.values()]
            elif isinstance(x, list): [walk(v) for v in x]
        walk(json.loads(text))
        return found
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        m = re.match(r'^"?[\w.\-]+"?\s*[=:]\s*"?(.*?)"?;?$', line)
        out.append(m.group(1) if m else line)
    return out


def check_strings(strings, doc):
    """Findings for a list of strings: (rule, string, reason)."""
    allowed, banned = table_values(doc), banned_list(doc)
    found = []
    for s in strings:
        if not re.search(r"[A-Za-z]", s):
            continue
        for w in banned_hits(s, banned):
            found.append(("LC-2", s, f"banned word '{w}'"))
        if s not in allowed:
            found.append(("LC-2", s, "not in the words table"))
        for why in plain_hits(s):
            found.append(("LC-31", s, why))
    return found


def find_lifecycle(root):
    d = Path(root) / "docs" / "design-system"
    nums = sorted((int(p.name[1:]) for p in d.glob("v[1-9]*") if p.name[1:].isdigit()), reverse=True)
    for name in [f"v{n}" for n in nums] + ["next-version"]:
        f = d / name / "lifecycle.json"
        if f.is_file():
            return f
    return None


def run(root, files=None):
    lc = find_lifecycle(root)
    if lc is None:
        print("words lint: no lifecycle.json under docs/design-system", file=sys.stderr)
        return 2
    doc = json.loads(lc.read_text(encoding="utf-8"))
    paths = files or [p for g in CONFIG["lifecycle_files"] for p in sorted(Path(root).glob(g))]
    bad = 0
    for p in paths:
        for rule, s, why in check_strings(literals(p, Path(p).read_text(encoding="utf-8")), doc):
            print(f"{rule} {p}: {why}: {s!r}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    root = sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else "."
    sys.exit(run(root))
