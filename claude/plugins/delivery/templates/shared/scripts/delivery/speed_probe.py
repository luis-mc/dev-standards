#!/usr/bin/env python3
"""Speed probe and `scaled(ms)` for timing budgets (CIR10 L7, owner answer 8).

A timing budget ("this call takes under 200 ms") means one thing on the machine it was set on and another
on a slower runner. The probe times a fixed workload, five runs, and takes the median. The scale is that
median divided by the reference time, never below 1, so a faster machine does not tighten a budget.

    speed_probe.py [--runs 5] [--reference-ms MS] [--max-scale 3] [--json] [--result FILE] [--export-env]
    speed_probe.py calibrate [--runs 5] [--file scripts/delivery/speed-probe.json]

Run it once at the start of the job that runs budgets. `--export-env` prints `DELIVERY_SPEED_SCALE=<n>`
for `$GITHUB_ENV`; `scaled()` here and `scaled.mjs` read that variable, so one probe serves the whole job.

A scale above `--max-scale` (default 3) is a refusal. The runner is too slow to judge a budget. The probe
exits 2 and `--result` writes `{"state": "error", ...}`, never `success`: a refusal is not a pass.

The reference time is the median on the machine the budgets were set on. `calibrate` writes it to
`scripts/delivery/speed-probe.json` (`{"reference_ms": N}`). Without that file the built-in
DEFAULT_REFERENCE_MS is used and the output says so.

Exit: 0 scale printed; 2 refused (state error); 64 usage error.
Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time

ENV_SCALE = "DELIVERY_SPEED_SCALE"
DEFAULT_RUNS = 5
DEFAULT_MAX_SCALE = 3.0
DEFAULT_REFERENCE_MS = 50.0
DEFAULT_FILE = "scripts/delivery/speed-probe.json"
EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 2, 64


class SpeedRefused(Exception):
    """The runner is too slow (or the scale is unreadable) to judge a timing budget."""


def workload() -> None:
    """Fixed work: hashing and sorting, no I/O, no threads. Do not change it without calibrating again."""
    h = b"delivery"
    for _ in range(60000):
        h = hashlib.sha256(h).digest()
    x, data = 12345, []
    for _ in range(60000):
        x = (x * 1103515245 + 12345) % 2147483648
        data.append(x)
    data.sort()


def probe(runs: int = DEFAULT_RUNS, work=workload, clock=time.perf_counter) -> float:
    """Median milliseconds of `runs` runs of the workload."""
    if runs < 1:
        raise ValueError("runs must be at least 1")
    times = []
    for _ in range(runs):
        t0 = clock()
        work()
        times.append((clock() - t0) * 1000.0)
    return statistics.median(times)


def scale_from(median_ms: float, reference_ms: float) -> float:
    """median / reference, never below 1."""
    if reference_ms <= 0:
        raise ValueError("reference_ms must be above 0")
    return max(1.0, median_ms / reference_ms)


def check_scale(scale: float, max_scale: float = DEFAULT_MAX_SCALE) -> float:
    if scale > max_scale:
        raise SpeedRefused("speed scale %.2f is above %.2f: this runner is too slow to judge timing budgets"
                           % (scale, max_scale))
    return scale


def read_reference(path: str = DEFAULT_FILE):
    """(reference_ms, from_file). A missing or unreadable file gives the built-in value."""
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f).get("reference_ms")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v), True
    except (OSError, ValueError, AttributeError):
        pass
    return DEFAULT_REFERENCE_MS, False


def get_scale(max_scale: float = DEFAULT_MAX_SCALE, env=None, reference_ms=None, runs: int = DEFAULT_RUNS) -> float:
    """The scale for this job. The variable DELIVERY_SPEED_SCALE wins (the job probed once); else probe now.
    An unreadable variable is a refusal, not scale 1: fail closed."""
    env = os.environ if env is None else env
    raw = env.get(ENV_SCALE)
    if raw not in (None, ""):
        try:
            v = float(raw)
        except ValueError:
            raise SpeedRefused("%s=%r is not a number" % (ENV_SCALE, raw))
        if not math.isfinite(v) or v <= 0:
            raise SpeedRefused("%s=%r is not a usable scale" % (ENV_SCALE, raw))
        return check_scale(max(1.0, v), max_scale)
    ref = reference_ms if reference_ms is not None else read_reference()[0]
    return check_scale(scale_from(probe(runs), ref), max_scale)


def scaled(ms, scale=None):
    """A budget in milliseconds for this runner. At scale 1 the result is `ms` itself; above 1 it rounds up."""
    s = get_scale() if scale is None else scale
    if s == 1:
        return ms
    return math.ceil(ms * s)


def _calibrate(args) -> int:
    ms = probe(args.runs)
    d = os.path.dirname(args.file)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(args.file, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"reference_ms": round(ms, 1), "runs": args.runs}, f, indent=2)
        f.write("\n")
    print("speed_probe: reference %.1f ms written to %s" % (ms, args.file))
    return EXIT_OK


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print("speed_probe: %s" % message, file=sys.stderr)
        sys.exit(EXIT_USAGE)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["calibrate"]:
        ap = _Parser(prog="speed_probe.py calibrate")
        ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
        ap.add_argument("--file", default=DEFAULT_FILE)
        a = ap.parse_args(argv[1:])
        return _calibrate(a) if a.runs >= 1 else ap.error("--runs must be at least 1")
    ap = _Parser(prog="speed_probe.py")
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    ap.add_argument("--reference-ms", type=float)
    ap.add_argument("--max-scale", type=float, default=DEFAULT_MAX_SCALE)
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--result", help="write {state, scale, ...} here; a refusal is state error")
    ap.add_argument("--export-env", action="store_true", help="print %s=<scale> for $GITHUB_ENV" % ENV_SCALE)
    a = ap.parse_args(argv)
    if a.runs < 1 or a.max_scale <= 0 or (a.reference_ms is not None and a.reference_ms <= 0):
        ap.error("--runs, --max-scale and --reference-ms must be positive")
    ref, from_file = (a.reference_ms, True) if a.reference_ms is not None else read_reference(a.file)
    med = probe(a.runs)
    scale = scale_from(med, ref)
    out = {"schema": 1, "median_ms": round(med, 1), "reference_ms": ref, "reference_from_file": from_file,
           "scale": round(scale, 3), "max_scale": a.max_scale, "state": "ok", "summary": ""}
    code = EXIT_OK
    try:
        check_scale(scale, a.max_scale)
    except SpeedRefused as exc:
        out["state"], out["summary"], code = "error", str(exc), EXIT_REFUSED
    if a.result:
        with open(a.result, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, indent=2)
            f.write("\n")
    if a.json:
        print(json.dumps(out))
    elif code:
        print("speed_probe: REFUSED. %s (median %.1f ms, reference %.1f ms)" % (out["summary"], med, ref),
              file=sys.stderr)
    elif a.export_env:
        print("%s=%s" % (ENV_SCALE, out["scale"]))
    else:
        print("speed_probe: scale %.3f (median %.1f ms, reference %.1f ms%s)"
              % (scale, med, ref, "" if from_file else ", built-in reference: run `calibrate`"))
    return code


if __name__ == "__main__":
    sys.exit(main())
