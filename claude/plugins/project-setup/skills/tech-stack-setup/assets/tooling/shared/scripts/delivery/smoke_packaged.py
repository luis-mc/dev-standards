#!/usr/bin/env python3
"""Start the packaged form of the product and check that every worker comes up (STACKSPEC 13.7).

    smoke_packaged.py [--config scripts/delivery/smoke.json] [--start CMD] [--expect TEXT ...]
                      [--health URL ...] [--timeout SECONDS] [--cwd DIR]

The declaration is a small JSON file, `scripts/delivery/smoke.json` by default:

    {"smoke": {"start": "./dist/app --port 8080",
               "expect": ["api ready", "worker-queue ready", "worker-mail ready"],
               "health": ["http://127.0.0.1:8080/healthz"],
               "timeout_s": 60,
               "cwd": "."}}

`start` is the command that runs the PACKAGED program (the built executable, the
installed bundle, `docker run` of the image), never the development server.
`expect` lists a readiness line for the program and for every child process or
worker it starts; each is looked for in the program's combined output, in any
order. `health` lists URLs that must answer 2xx. The run passes when every line
has been seen and every probe has answered before `timeout_s` (default 60); it
fails (exit 1) when the program exits first or a line never shows, naming each
one missing. The whole process tree is stopped at the end, on success and on
failure; only processes this script started are touched.

A declaration with an empty `start` means the product ships no packaged program:
the script says so on stdout and exits 0. A product that does ship one MUST NOT
leave it empty (STACKSPEC 13.7); an empty `expect` with a `start` is refused
(exit 2), because a program that started but whose workers were never looked at
is the failure this check exists for.

Exit: 0 passed or nothing to check, 1 failed, 2 usage or configuration, 4 timed out.
Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True

import delivery_common as dc

DEFAULT_CONFIG = "scripts/delivery/smoke.json"
DEFAULT_TIMEOUT = 60.0
KEEP_LINES = 40  # the last lines of output shown when the run fails


def load_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise dc.DeliveryError("%s not found" % path)
    except (OSError, json.JSONDecodeError) as exc:
        raise dc.DeliveryError("cannot read %s: %s" % (path, exc))
    smoke = data.get("smoke") if isinstance(data, dict) else None
    if not isinstance(smoke, dict):
        raise dc.DeliveryError('%s has no "smoke" object' % path)
    return smoke


def settings(args: argparse.Namespace, root: Path) -> dict:
    cfg: dict = {}
    config = Path(args.config) if args.config else root / DEFAULT_CONFIG
    if args.config or not args.start:  # a missing declaration is an error, never a silent pass
        cfg = load_config(config if config.is_absolute() else root / config)
    if args.start is not None:
        cfg["start"] = args.start
    if args.expect:
        cfg["expect"] = args.expect
    if args.health:
        cfg["health"] = args.health
    if args.timeout is not None:
        cfg["timeout_s"] = args.timeout
    if args.cwd is not None:
        cfg["cwd"] = args.cwd
    start = cfg.get("start") or ""
    expect = cfg.get("expect") or []
    health = cfg.get("health") or []
    if not isinstance(start, str) or not all(isinstance(x, str) and x for x in [*expect, *health]):
        raise dc.DeliveryError('"start" must be a string, "expect" and "health" lists of non-empty strings')
    if not isinstance(expect, list) or not isinstance(health, list):
        raise dc.DeliveryError('"expect" and "health" must be lists')
    timeout = cfg.get("timeout_s", DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise dc.DeliveryError('"timeout_s" must be a positive number')
    if start.strip() and not expect and not health:
        raise dc.DeliveryError('"expect" is empty: list a readiness line for the program and for each worker it starts')
    return {"start": start.strip(), "expect": expect, "health": health, "timeout": float(timeout),
            "cwd": cfg.get("cwd") or "."}


# --------------------------------------------------------------------------
# the process
# --------------------------------------------------------------------------

def spawn(command: str, cwd: Path) -> subprocess.Popen:
    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)


def stop_tree(proc: subprocess.Popen) -> None:
    """Stop the process and everything it started. Only the tree rooted at `proc`."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and proc.poll() is None:
                time.sleep(0.1)
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def pump(stream, lines: "queue.Queue[str | None]") -> None:
    try:
        for line in stream:
            lines.put(line.rstrip("\r\n"))
    finally:
        lines.put(None)


def probe(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310 - the product's own health URL
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def run_smoke(cfg: dict, root: Path) -> int:
    cwd = (root / cfg["cwd"]).resolve()
    if not cwd.is_dir():
        raise dc.DeliveryError("cwd '%s' is not a directory" % cfg["cwd"])
    waiting = list(cfg["expect"])
    probes = list(cfg["health"])
    seen: list[str] = []
    tail: list[str] = []
    proc = spawn(cfg["start"], cwd)
    lines: "queue.Queue[str | None]" = queue.Queue()
    threading.Thread(target=pump, args=(proc.stdout, lines), daemon=True).start()
    deadline = time.monotonic() + cfg["timeout"]
    exited = False
    try:
        while waiting or probes:
            if time.monotonic() >= deadline:
                break
            try:
                line = lines.get(timeout=0.25)
            except queue.Empty:
                line = ""
            if line is None:
                exited = True
                # the pipe closed: the program (and every holder of its output) is gone
                break
            if line:
                tail = (tail + [line])[-KEEP_LINES:]
                for want in [w for w in waiting if w in line]:
                    waiting.remove(want)
                    seen.append(want)
                    print("smoke: ready: %s" % want)
            if probes:
                for url in [u for u in probes if probe(u)]:
                    probes.remove(url)
                    print("smoke: healthy: %s" % url)
            if not waiting and not probes:
                break
            if proc.poll() is not None and lines.empty():
                exited = True
                break
    finally:
        code = proc.poll()
        if code is None and exited:  # the pipe closed a moment before the exit status was readable
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        stop_tree(proc)
    if not waiting and not probes:
        print("smoke: passed (%d readiness line(s), %d probe(s))" % (len(seen), len(cfg["health"])))
        return dc.EXIT_OK
    missing = ["line: %s" % w for w in waiting] + ["health: %s" % u for u in probes]
    why = ("the program exited%s before everything was ready" % ("" if code is None else " with code %s" % code)
           if exited else "timed out after %g s" % cfg["timeout"])
    dc.eprint("smoke: FAILED, %s. Not ready:" % why)
    for m in missing:
        dc.eprint("  - " + m)
    if tail:
        dc.eprint("smoke: last output:")
        for line in tail:
            dc.eprint("  | " + line)
    return dc.EXIT_FAIL if exited else dc.EXIT_TIMEOUT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smoke_packaged.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", metavar="FILE", help="the declaration (default: %s)" % DEFAULT_CONFIG)
    ap.add_argument("--start", metavar="CMD", help="the command that starts the packaged program")
    ap.add_argument("--expect", action="append", metavar="TEXT", help="a readiness line to wait for (repeatable)")
    ap.add_argument("--health", action="append", metavar="URL", help="a URL that must answer 2xx (repeatable)")
    ap.add_argument("--timeout", type=float, metavar="SECONDS")
    ap.add_argument("--cwd", metavar="DIR")
    args = ap.parse_args(argv)
    root = dc.repo_root()
    cfg = settings(args, root)
    if not cfg["start"]:
        print("smoke: no packaged program declared (start is empty); nothing to start")
        return dc.EXIT_OK
    return run_smoke(cfg, root)


if __name__ == "__main__":
    dc.main_guard(main)
