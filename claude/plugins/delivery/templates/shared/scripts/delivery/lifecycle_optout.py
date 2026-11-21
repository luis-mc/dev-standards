#!/usr/bin/env python3
"""DS235d: lifecycle opt-outs (LC-27).

`.delivery/config.json` may turn a lifecycle check off:
  {"lifecycle": {"off": {"LC-16": {"decision": "D123", "reason": "...", "review": "2027-03-01"}}}}
An opt-out needs a decision ID, a reason and a review date that is not past. `check` fails on a bad one and
prints, one line per check, what the opt-out loses. `line` prints the one line the session hook shows.

  lifecycle_optout.py check [--config .delivery/config.json] [--today YYYY-MM-DD]
  lifecycle_optout.py line  [--config .delivery/config.json]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

IMPACT = {
    "LC-8": "no proof that a fresh install passes its own self-test",
    "LC-9": "no proof that a silent install exits 0, needs no reboot and brings the service up in 30 s",
    "LC-10": "a reinstall of the same version may change config or data without anyone noticing",
    "LC-11": "an upgrade from the previous version may lose config or data without anyone noticing",
    "LC-12": "a broken build may stay installed with no rollback",
    "LC-13": "an older build may replace a newer one",
    "LC-14": "remove may delete data the owner chose to keep, or leave data behind",
    "LC-15": "purge may leave files, services, tasks, keys or ports behind",
    "LC-16": "remove may fail or ask for a reboot while the tray runs",
    "LC-17": "the service may not start when nobody is signed in",
    "LC-18": "the Windows installer is not checked for ICE errors or a double Apps-list entry",
    "LC-19": "the Linux package is not linted and may not install where systemd is not running",
    "LC-20": "the service unit is not verified and may run as root",
    "LC-21": "the macOS package signature and notarization are not checked",
    "LC-29": "the service may need a manual step after pairing",
    "LC-32": "artifact names may drift and public packages may share a store with private data",
    "LC-33": "a product may keep more than one data folder, or leave a legacy folder",
}


def load(config):
    try:
        return json.loads(Path(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def entries(cfg):
    off = ((cfg.get("lifecycle") or {}).get("off")) or {}
    return off if isinstance(off, dict) else {}


def _num(check):
    digits = "".join(c for c in str(check) if c.isdigit())
    return (int(digits) if digits else 0, str(check))


def parse_day(s):
    try:
        return datetime.date.fromisoformat(str(s))
    except ValueError:
        return None


def problems(cfg, today=None):
    today = today or datetime.date.today()
    out = []
    for check, e in sorted(entries(cfg).items(), key=lambda kv: _num(kv[0])):
        e = e if isinstance(e, dict) else {}
        if not e.get("decision"):
            out.append("%s: opt-out has no decision ID" % check)
        if not e.get("reason"):
            out.append("%s: opt-out has no reason" % check)
        day = parse_day(e.get("review"))
        if day is None:
            out.append("%s: opt-out has no review date (YYYY-MM-DD)" % check)
        elif day < today:
            out.append("%s: review date %s is past" % (check, day))
    return out


def impact_lines(cfg):
    return ["%s off loses: %s" % (c, IMPACT.get(c, "the check named by this ID (no text recorded)"))
            for c in sorted(entries(cfg), key=_num)]


def hook_line(cfg):
    """One line for the session hook; empty when nothing is opted out."""
    off = sorted(entries(cfg), key=_num)
    return "Lifecycle checks off: " + ", ".join(off) if off else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["check", "line"])
    ap.add_argument("--config", default=".delivery/config.json")
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    cfg = load(a.config)
    if a.cmd == "line":
        print(hook_line(cfg))
        return 0
    bad = problems(cfg, parse_day(a.today) if a.today else None)
    for line in impact_lines(cfg):
        print(line)
    for b in bad:
        print("FAIL " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
