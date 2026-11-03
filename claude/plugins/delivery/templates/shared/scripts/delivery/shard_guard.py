#!/usr/bin/env python3
"""Shard-table guard (DL19, CIR10 L3): every test file is in exactly one shard, and every shard fits its limits.

    shard_guard.py check [--table scripts/delivery/ci-shards.json] [--root .] [--json]

Fails (exit 1) when
  * a test file of a suite is in no shard, or in two shards of the same OS;
  * a suite has no shard, matches no files, or its `part` shards do not cover 1..N once each;
  * an `members` glob matches nothing;
  * a shard's `size` is over the table's `limits` (cpus, memory_gib, timeout_min) or has more workers than cpus;
  * the estimated time of a shard (recorded seconds of its files over its workers) is over its timeout.

Exit 2 when the table or the timings file cannot be read. Run it in the product's fast test run, so a new test
file that no shard names fails the pull request that adds it. The shard rules are in CONTRACT.md. Standard
library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shard_table as st  # noqa: E402


def check(table: dict, root: Path):
    """Returns (problems, rows). rows = one dict per shard: id, files, estimate_s, timeout_min."""
    assignment, problems = st.resolve(table, root)
    suites = table.get("suites") if isinstance(table.get("suites"), dict) else {}
    rows = []
    for sh in table["shards"]:
        if not isinstance(sh, dict):
            continue
        sid = str(sh.get("id"))
        problems += st.size_problems(sh, table)
        row = {"id": sid, "files": None, "estimate_s": None, "timeout_min": st.size_of(sh, table)["timeout_min"]}
        if sid in assignment:
            files = assignment[sid]
            size = st.size_of(sh, table)
            workers = size["workers"] if isinstance(size["workers"], int) and size["workers"] >= 1 else 1
            timings = st._timings(table, suites.get(sh.get("suite"), {}), root)
            row["files"] = len(files)
            row["estimate_s"] = round(st.estimate_seconds(files, timings, workers), 1)
            t = row["timeout_min"]
            if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 and row["estimate_s"] > t * 60:
                problems.append("shard %s: estimated %.0f s is over its timeout of %s min" %
                                (sid, row["estimate_s"], t))
        rows.append(row)
    return sorted(set(problems)), rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="check that every test file is in exactly one shard")
    ap.add_argument("action", choices=["check"])
    ap.add_argument("--table", default=st.DEFAULT_TABLE)
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root)
    try:
        table = st.load_table(root / args.table)
        problems, rows = check(table, root)
    except (OSError, ValueError) as exc:
        print("shard_guard: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems, "shards": rows}, indent=1))
    else:
        for r in rows:
            if r["files"] is not None:
                print("shard_guard: %-24s %4d files, about %s s" % (r["id"], r["files"], r["estimate_s"]))
        for p in problems:
            print("shard_guard: FAIL %s" % p, file=sys.stderr)
        if not problems:
            print("shard_guard: ok, %d shard(s)" % len(rows))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
