#!/usr/bin/env python3
"""Delivery rule ids in code exist in DELIVERYSPEC, and its Today column matches the hooks (DS303).

1. Every DL-n and Q-n that a delivery hook or script names (`scripts/*.py`, `templates/**/*.py` of the
   delivery plugin) is a row of DELIVERYSPEC section 1, or an id listed under "Removed rules".
2. A rule key of a hook is a live row, never a retired one. A rule key is an id that opens a string:
   a `check_on` key, a finding key or a deny or warning message.
3. The Today column matches the hook registry. A live row whose id is a key of `hook_pre_tool.py` or
   `hook_stop.py` says Y, W or ~ and names that file. A row whose Today cell names one of those files is
   a key of it or is cited in it (a rule that shapes another rule's check, like DL-130). A key that only warns
   (never denies or blocks) says W.
4. The counts line under the tables matches the rows. `--fix` rewrites it.

Run:  python3 claude/plugins/delivery/tests/test_rule_ids.py [--fix]
Exit: 0 all passed, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[4]
PLUGIN = REPO / "claude" / "plugins" / "delivery"
SPEC = PLUGIN / "references" / "deliveryspec.md"
HOOKS = ("hook_pre_tool.py", "hook_stop.py")

ROW_RE = re.compile(r"^\| ((?:DL-(?:\d{2,3}[a-z]?|LC\d+))|Q-\d+) \|", re.M)
CITE_RE = re.compile(r"\b(DL-\d{1,3}[a-z]?|Q-\d+)\b")
KEY_RE = re.compile(r"(?<!['\"])['\"](DL-\d{2,3}[a-z]?|Q-\d+)(?=[ :'\"])")
DENY_RE = re.compile(r"deny\(\s*['\"](DL-\d{2,3}[a-z]?|Q-\d+)\b")
WARN_RETURN_RE = re.compile(r"return \(?\s*['\"](DL-\d{2,3}[a-z]?|Q-\d+) ")
WARN_ONLY_RE = re.compile(r"^WARN_ONLY = \(([^)]*)\)", re.M)
RETIRED_RE = re.compile(r"^\s*(removed|merged into|retired)\b", re.I)
REMOVED_RE = re.compile(r"These IDs are removed and are not reused: ([^.]+)\.")
COUNTS_RE = re.compile(r"^Counts: .*$", re.M)


def cells(line: str) -> list[str]:
    """The cells of one table row; `\\|` inside a cell is text, not a column break."""
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def spec_rows(text: str) -> dict[str, dict]:
    """id -> {retired, today} for every row of section 1."""
    body = text.split("## 1. Rules", 1)[-1].split("## 2.", 1)[0]
    rows: dict[str, dict] = {}
    for line in body.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        c = cells(line)
        retired = len(c) < 7 or bool(RETIRED_RE.match(c[1]))
        rows[m.group(1)] = {"retired": retired, "today": "" if retired else c[6]}
    return rows


def removed_ids(text: str) -> set[str]:
    m = REMOVED_RE.search(text)
    return set(CITE_RE.findall(m.group(1))) if m else set()


def code_files() -> list[Path]:
    files = sorted((PLUGIN / "scripts").glob("*.py")) + sorted((PLUGIN / "templates").rglob("*.py"))
    return [f for f in files if f.is_file()]


def hook_keys(source: str) -> tuple[set[str], set[str]]:
    """(rule keys, keys that only warn) of one hook's source."""
    keys = set(KEY_RE.findall(source))
    denies = set(DENY_RE.findall(source))
    warn = set(WARN_RETURN_RE.findall(source)) - denies
    m = WARN_ONLY_RE.search(source)
    if m:
        warn |= set(CITE_RE.findall(m.group(1)))
    return keys, warn


def counts_line(rows: dict[str, dict]) -> str:
    live = [r for r in rows.values() if not r["retired"]]
    dl = sum(1 for i, r in rows.items() if not r["retired"] and i.startswith("DL-"))
    q = sum(1 for i, r in rows.items() if not r["retired"] and i.startswith("Q-"))
    tally = {k: sum(1 for r in live if r["today"][:1] == k) for k in "YW~N"}
    return ("Counts: %d rows in section 1: %d live rules (%d DL, %d Q) and %d retired or removed rows. "
            "Today: %d Y, %d W, %d ~, %d N. `claude/plugins/delivery/tests/test_rule_ids.py` checks this line and the Today column."
            % (len(rows), len(live), dl, q, len(rows) - len(live), tally["Y"], tally["W"], tally["~"], tally["N"]))


def problems(text: str, sources: dict[str, str], hooks: dict[str, str]) -> list[str]:
    """Findings. `sources` maps a code path to its text; `hooks` maps a hook file name to its text."""
    rows = spec_rows(text)
    known = set(rows) | removed_ids(text)
    found: list[str] = []
    for rel, src in sorted(sources.items()):
        for no, line in enumerate(src.splitlines(), 1):
            for rid in CITE_RE.findall(line):
                if rid not in known:
                    found.append("%s:%d: %s is not a DELIVERYSPEC rule" % (rel, no, rid))
    for name, src in sorted(hooks.items()):
        keys, warn = hook_keys(src)
        for rid in sorted(keys):
            row = rows.get(rid)
            if row is None:
                continue                                  # reported above
            if row["retired"]:
                found.append("%s: rule key %s is a retired row" % (name, rid))
                continue
            today = row["today"]
            if today[:1] not in "YW~" or name not in today:
                found.append("%s: %s is checked by %s, but its Today cell says: %s" % (rid, name, name, today or "-"))
            if rid in warn and today[:1] != "W":
                found.append("%s: %s only warns, but its Today cell does not start with W: %s" % (rid, name, today))
        cited = set(CITE_RE.findall(src))
        for rid, row in sorted(rows.items()):
            if not row["retired"] and name in row["today"] and rid not in keys | cited:
                found.append("%s: Today names %s, but that hook neither checks nor cites %s" % (rid, name, rid))
    m = COUNTS_RE.search(text)
    want = counts_line(rows)
    if not m:
        found.append("DELIVERYSPEC has no counts line")
    elif m.group(0) != want:
        found.append("counts line is stale; run python3 claude/plugins/delivery/tests/test_rule_ids.py --fix\n    is:   %s\n    want: %s"
                     % (m.group(0), want))
    return found


def selftest() -> list[str]:
    """The checks above must be able to fail."""
    bad: list[str] = []
    spec = ("## 1. Rules\n"
            "| DL-01 | Do x. | s | G | PRE | r | Y `hook_pre_tool.py` |\n"
            "| DL-02 | Do y. | s | G | STOP | r | N |\n"
            "| DL-03 | Merged into Q-1. |\n"
            "| Q-1 | Ask. | s | G | PRE | a \\| b | W `hook_pre_tool.py` |\n"
            "## 2. Ledger\n")
    ok_hook = ("def f():\n    if check_on(cfg, 'DL-01'):\n        deny('DL-01 no')\n"
               "def g():\n    return ('Q-1 said once')\n")
    line = counts_line(spec_rows(spec))
    good = spec.replace("## 2. Ledger", line + "\n## 2. Ledger")
    if problems(good, {"a.py": "# DL-02, DL-03"}, {"hook_pre_tool.py": ok_hook}):
        bad.append("a consistent spec was refused: %s" % problems(good, {}, {"hook_pre_tool.py": ok_hook}))
    if not problems(good, {"a.py": "# DL-99"}, {}):
        bad.append("an id missing from the spec was not reported")
    if not problems(good, {}, {"hook_pre_tool.py": ok_hook + "deny('DL-02 no')\n"}):
        bad.append("a hook key whose Today says N was not reported")
    if not problems(good, {}, {"hook_pre_tool.py": ok_hook + "deny('DL-03 no')\n"}):
        bad.append("a hook key on a retired row was not reported")
    if not problems(good, {}, {"hook_pre_tool.py": "deny('Q-1 no')\n"}):
        bad.append("a Today cell naming a hook that lacks the key was not reported")
    warn_spec = good.replace("W `hook_pre_tool.py`", "Y `hook_pre_tool.py`")
    if not problems(warn_spec, {}, {"hook_pre_tool.py": ok_hook}):
        bad.append("a warning-only key marked Y was not reported")
    if not problems(spec + "Counts: 1 rule.\n", {}, {}):
        bad.append("a stale counts line was not reported")
    if spec_rows(spec)["Q-1"]["today"] != "W `hook_pre_tool.py`":
        bad.append("an escaped pipe split a cell")
    return bad


def main(argv: list[str]) -> int:
    text = SPEC.read_text(encoding="utf-8")
    if "--fix" in argv:
        new = COUNTS_RE.sub(lambda _m: counts_line(spec_rows(text)), text, count=1)
        if new != text:
            SPEC.write_text(new, encoding="utf-8")
            print("counts line rewritten")
            text = new
    sources = {str(f.relative_to(REPO)): f.read_text(encoding="utf-8") for f in code_files()}
    hooks = {h: (PLUGIN / "scripts" / h).read_text(encoding="utf-8") for h in HOOKS}
    bad = ["self-test: " + m for m in selftest()] + problems(text, sources, hooks)
    for m in bad:
        print("  " + m)
    print("%s: %d code files, %d rows in DELIVERYSPEC section 1"
          % ("PASSED" if not bad else "FAILED (%d)" % len(bad), len(sources), len(spec_rows(text))))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
