#!/usr/bin/env python3
"""The required check treats a carried job as passed (DS287, R5.91).

    carry_verify.py --needs '<toJSON(needs)>' --carried '<carry plan json>' [--summary FILE] [--ignore a,b]

Passes (exit 0) when every needed job is `success`, or is `skipped` and named in `carried`.
Fails (exit 1) on any other result, and on a skipped job that is not carried.
`--ignore` names jobs left out of the check (plumbing such as `decide` and `plan`, or a job the runner plan or
the runner kind skips on purpose). Writes a markdown table (job | result | proved by) to --summary (default $GITHUB_STEP_SUMMARY).
`carried` is {job: {"sha": ..., "run_url": ...}}. Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _load(text: str, what: str) -> dict:
    if not (text or "").strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        raise SystemExit(f"carry_verify: {what} is not JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"carry_verify: {what} must be a JSON object")
    return data


def verify(needs: dict, carried: dict) -> tuple[bool, list[tuple[str, str, str, bool]]]:
    """Return (ok, rows). A row is (job, result, proof, ok)."""
    rows = []
    for job, info in needs.items():
        result = info.get("result", "") if isinstance(info, dict) else str(info)
        proof, ok = "", False
        if result == "success":
            ok = True
        elif result == "skipped" and job in carried:
            ok = True
            c = carried[job] if isinstance(carried[job], dict) else {}
            url, sha = c.get("run_url", ""), c.get("sha", "")
            proof = f"[{sha[:7] or 'earlier run'}]({url})" if url else (sha[:7] or "carried")
            result = "carried"
        rows.append((job, result, proof, ok))
    return all(r[3] for r in rows), rows


def table(rows) -> str:
    out = ["| job | result | proved by |", "| --- | --- | --- |"]
    for job, result, proof, ok in rows:
        out.append(f"| {job} | {result}{'' if ok else ' (not passed)'} | {proof or '-'} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--needs", required=True)
    ap.add_argument("--carried", default="{}")
    ap.add_argument("--ignore", default="")
    ap.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY", ""))
    a = ap.parse_args(argv)
    needs = _load(a.needs, "--needs")
    for name in a.ignore.split(","):
        needs.pop(name.strip(), None)
    ok, rows = verify(needs, _load(a.carried, "--carried"))
    text = table(rows)
    print(text)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(text)
    bad = [r[0] for r in rows if not r[3]]
    print("ok" if ok else "not green: " + ", ".join(bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
