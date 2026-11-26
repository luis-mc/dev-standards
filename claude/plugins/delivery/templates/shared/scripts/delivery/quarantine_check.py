#!/usr/bin/env python3
"""DS264: the flake quarantine (S9 of the CI review; DL-99 G3 allows no retry).

`.delivery/quarantine.json` lists the tests that are out of the blocking step:
  {"tests": [{"test": "TestJoinsItsOwnAgent", "task": "DS300", "review": "2026-12-05",
              "reason": "temp dir cleanup race under -race", "suite": "go"}]}
`test`, `task` (the owner task that fixes it) and `review` (YYYY-MM-DD) are required; `reason` and `suite` are notes.
A quarantined test is never retried until it passes. The project's blocking step leaves it out (for example
`go test -skip`, or the e2e quarantine list) and a non-blocking step runs it and reports. `check` fails an entry with
no task ID or a review date that is past, and prints one plain line per entry saying what it loses. `line` prints the
one line the session hook shows. `names` prints the quarantined test names, one per line, for the project's steps.

  quarantine_check.py check [--file .delivery/quarantine.json] [--today YYYY-MM-DD]
  quarantine_check.py line  [--file .delivery/quarantine.json]
  quarantine_check.py names [--file .delivery/quarantine.json]

Exit 0 when every entry is valid or the file is absent, 1 when an entry fails. Standard library only.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

DEFAULT_FILE = ".delivery/quarantine.json"


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def entries(data):
    tests = data.get("tests") if isinstance(data, dict) else None
    return [e if isinstance(e, dict) else {} for e in tests] if isinstance(tests, list) else []


def _name(e, i):
    return str(e.get("test") or "entry %d" % (i + 1))


def parse_day(s):
    try:
        return datetime.date.fromisoformat(str(s))
    except ValueError:
        return None


def problems(data, today=None):
    today = today or datetime.date.today()
    out = []
    for i, e in enumerate(entries(data)):
        name = _name(e, i)
        if not e.get("test"):
            out.append("%s: no test name" % name)
        if not e.get("task"):
            out.append("%s: quarantine has no task ID" % name)
        day = parse_day(e.get("review"))
        if day is None:
            out.append("%s: quarantine has no review date (YYYY-MM-DD)" % name)
        elif day < today:
            out.append("%s: review date %s is past" % (name, day))
    return out


def impact_lines(data):
    return ["%s quarantined loses: a failure of it no longer blocks a merge; it runs in a non-blocking step and reports"
            % _name(e, i) for i, e in enumerate(entries(data))]


def hook_line(data):
    """One line for the session hook; empty when nothing is quarantined."""
    names = [_name(e, i) for i, e in enumerate(entries(data))]
    return "Quarantined tests (%d): %s" % (len(names), ", ".join(names)) if names else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["check", "line", "names"])
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    data = load(a.file)
    if a.cmd == "line":
        print(hook_line(data))
        return 0
    if a.cmd == "names":
        for i, e in enumerate(entries(data)):
            if e.get("test"):
                print(e["test"])
        return 0
    bad = problems(data, parse_day(a.today) if a.today else None)
    for line in impact_lines(data):
        print(line)
    for b in bad:
        print("FAIL " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
