#!/usr/bin/env python3
"""DL168: measured durations from the delivery ledger, for sizing an ETA.

  python delivery_eta.py --root . --kind agent|ci|join|pool-refresh [--where cloud|local] [--last 20] [--json]

Prints the median and p75 in minutes, the sample size, and 'no history' with fewer than 3 samples.
Importable: estimate(root, kind, where=None, last=20) -> dict.
Standard library only.
"""
import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

KINDS = ("agent", "ci", "join", "pool-refresh")
MIN_SAMPLES = 3


def _ts(text):
    if not isinstance(text, str) or not text:
        return None
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _span(start, end):
    a, b = _ts(start), _ts(end)
    if a is None or b is None or b < a:
        return None
    return b, (b - a).total_seconds() / 60.0


def _load(root):
    try:
        data = json.loads((Path(root) / ".delivery" / "ledger.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _rows(led, kind, where):
    """(end time, minutes) pairs for one kind."""
    out = []

    def add(rows, start_key, end_keys, keep=lambda r: True):
        for r in rows or []:
            if not isinstance(r, dict) or not keep(r):
                continue
            end = next((r.get(k) for k in end_keys if r.get(k)), None)
            got = _span(r.get(start_key), end)
            if got:
                out.append(got)

    if kind == "agent":
        add(led.get("agents"), "started", ("finished_at",),
            lambda r: r.get("state") == "done" and (where is None or r.get("where") == where))
    elif kind == "ci":
        for t in led.get("trains") or []:
            ci = t.get("ci") if isinstance(t, dict) else None
            if isinstance(ci, dict):
                got = _span(ci.get("run_started_at"), ci.get("run_completed_at"))
                if got:
                    out.append(got)
    elif kind == "join":
        add(led.get("trains"), "joined_at", ("pushed_at",))
    elif kind == "pool-refresh":
        add(led.get("jobs"), "started", ("ended", "finished_at"), lambda r: r.get("kind") == "pool-refresh")
    return out


def _p75(values):
    v = sorted(values)
    k = max(0, math.ceil(0.75 * len(v)) - 1)
    return v[k]


def estimate(root, kind, where=None, last=20):
    """{'kind', 'where', 'n', 'median', 'p75', 'history'}; median and p75 are None without 3 samples."""
    return estimate_ledger(_load(root), kind, where, last)


def estimate_ledger(led, kind, where=None, last=20):
    """Same as estimate, from a ledger dict already in memory."""
    if kind not in KINDS:
        raise ValueError("kind must be one of %s" % ", ".join(KINDS))
    rows = sorted(_rows(led or {}, kind, where), key=lambda x: x[0])[-max(1, int(last)):]
    mins = [m for _, m in rows]
    res = {"kind": kind, "where": where, "n": len(mins), "median": None, "p75": None, "history": len(mins) >= MIN_SAMPLES}
    if len(mins) >= MIN_SAMPLES:
        res["median"] = round(statistics.median(mins), 1)
        res["p75"] = round(_p75(mins), 1)
    return res


def describe(res):
    if not res["history"]:
        return "%s: no history (%d samples, need %d)" % (res["kind"], res["n"], MIN_SAMPLES)
    return "%s%s: median %.1f min, p75 %.1f min, %d samples" % (
        res["kind"], " (%s)" % res["where"] if res["where"] else "", res["median"], res["p75"], res["n"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--where", choices=("cloud", "local"))
    ap.add_argument("--last", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = estimate(args.root, args.kind, args.where, args.last)
    print(json.dumps(res) if args.json else describe(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
