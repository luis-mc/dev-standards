#!/usr/bin/env python3
"""Prove smoke_packaged.py does what CONTRACT.md and STACKSPEC 13.7 say.

Each scenario builds a throwaway git repository holding the delivery scripts and a
fake "packaged program": a small Python script that prints readiness lines for
itself and for the worker processes it starts. The script under test must pass
when every worker reports, fail when one does not (the program exiting, or
staying up without it), stop the whole process tree on every path, and refuse a
declaration that would check nothing. The track templates' smoke.json files and
package.yml workflows are checked structurally.

"Every check must be able to fail" is proved as in tools/test_delivery_gate.py: the
mutation pass copies the scripts, breaks one rule in the copy and requires the
scenario that guards it to fail.

Run:  python3 tools/test_smoke_packaged.py [--no-mutants] [-k SUBSTRING]
Exit: 0 all passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_delivery_gate as tdg  # noqa: E402  (its harness: T, run, mutated_shared)
from test_delivery_gate import PY, SHARED, T, run  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="smoke-packaged-test-"))
S = "scripts/delivery/smoke_packaged.py"
TRACKS = ("ts", "go", "rust", "dotnet")

# A fake packaged program. argv: <mode> <pid-file>. It starts one worker process
# (which records its pid), prints readiness lines, then stays up (or exits).
PROGRAM = r'''
import os, subprocess, sys, time
mode, pidfile = sys.argv[1], sys.argv[2]
worker = "import os, sys, time\nopen(sys.argv[1], 'a').write(str(os.getpid()) + '\\n')\n" \
         "print('worker-queue ready', flush=True)\ntime.sleep(60)\n"
if mode == "exit":
    print("starting", flush=True)
    sys.exit(3)
subprocess.Popen([sys.executable, "-c", worker, pidfile])
print("api ready", flush=True)
if mode == "all":
    # a second worker that is also started
    subprocess.Popen([sys.executable, "-c", worker.replace("worker-queue", "worker-mail"), pidfile])
elif mode == "noisy":
    print("worker-mail failed to start: connection refused", flush=True)
open(pidfile, "a").write(str(os.getpid()) + "\n")
if mode == "crash-after":
    time.sleep(1)
    sys.exit(1)
time.sleep(60)
'''


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap(pidfile: Path) -> None:
    """Stop what a scenario's fake program left (a mutant may leave it): only pids it wrote itself."""
    for pid in alive_pids(pidfile):
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        else:
            try:
                os.kill(pid, 9)
            except OSError:
                pass


def alive_pids(pidfile: Path) -> list[int]:
    if not pidfile.exists():
        return []
    return [p for p in (int(x) for x in pidfile.read_text().split()) if pid_alive(p)]


class Repo:
    def __init__(self, shared: Path) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="repo-", dir=_TMP))
        run(["git", "init", "-q", "-b", "main"], cwd=self.root)
        d = self.root / "scripts/delivery"
        d.mkdir(parents=True)
        for name in ("delivery_common.py", "smoke_packaged.py"):
            tdg.Box.copy_text(shared / "scripts/delivery" / name, d / name)
        (self.root / "program.py").write_text(PROGRAM, encoding="utf-8")
        self.pids = self.root / "pids.txt"

    def start_cmd(self, mode: str) -> str:
        q = lambda p: '"%s"' % str(p).replace("\\", "/")  # noqa: E731
        return "%s %s %s %s" % (q(PY), q(self.root / "program.py"), mode, q(self.pids))

    def declare(self, smoke: dict) -> None:
        (self.root / "scripts/delivery/smoke.json").write_text(json.dumps({"smoke": smoke}), encoding="utf-8")

    def smoke(self, *args: str):
        return run([PY, str(self.root / S), *args], cwd=self.root)


def sc_workers(t: T, shared: Path) -> None:
    r = Repo(shared)
    r.declare({"start": r.start_cmd("all"), "expect": ["api ready", "worker-queue ready", "worker-mail ready"], "timeout_s": 20})
    res = r.smoke()
    t.check("every worker reports: exit 0", res.code == 0, res.text)
    t.has("... says passed", res.out, "smoke: passed")
    time.sleep(0.5)
    t.eq("... and the program and both workers are stopped", alive_pids(r.pids), [])
    reap(r.pids)

    # a worker that never reports while the program stays up: fails by timeout, names the worker
    r = Repo(shared)
    r.declare({"start": r.start_cmd("one"), "expect": ["api ready", "worker-queue ready", "worker-mail ready"], "timeout_s": 4})
    res = r.smoke()
    t.eq("a worker that never reports: exit 4 (timed out)", res.code, 4)
    t.has("... names the missing worker", res.err, "worker-mail ready")
    t.check("... and does not name the ones that came up", "line: api ready" not in res.err and "line: worker-queue ready" not in res.err, res.err)
    time.sleep(0.5)
    t.eq("... the tree is stopped on failure too", alive_pids(r.pids), [])
    reap(r.pids)

    # a worker that reports failure instead: the line it must print is still absent
    r = Repo(shared)
    r.declare({"start": r.start_cmd("noisy"), "expect": ["api ready", "worker-mail ready"], "timeout_s": 4})
    res = r.smoke()
    t.check("a worker that logs a failure instead of ready: fails", res.code != 0, res.text)
    t.has("... shows the output so the cause is visible", res.err, "connection refused")
    time.sleep(0.5)
    reap(r.pids)

    # the program itself exits first
    r = Repo(shared)
    r.declare({"start": r.start_cmd("exit"), "expect": ["api ready"], "timeout_s": 20})
    res = r.smoke()
    t.eq("the program exits before it is ready: exit 1", res.code, 1)
    t.has("... says it exited", res.err, "exited")
    t.has("... with its code", res.err, "code 3")

    # command-line form, no file
    r = Repo(shared)
    res = r.smoke("--start", r.start_cmd("all"), "--expect", "worker-mail ready", "--timeout", "20")
    t.check("--start / --expect without a declaration file", res.code == 0, res.text)


def sc_stop_tree(t: T, shared: Path) -> None:
    r = Repo(shared)
    r.declare({"start": r.start_cmd("all"), "expect": ["worker-mail ready"], "timeout_s": 20})
    res = r.smoke()
    t.check("passed", res.code == 0, res.text)
    pids = [int(x) for x in r.pids.read_text().split()] if r.pids.exists() else []
    t.check("the program and its workers wrote their pids", len(pids) >= 3, str(pids))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and any(pid_alive(p) for p in pids):
        time.sleep(0.2)
    t.eq("none of them is running afterwards", [p for p in pids if pid_alive(p)], [])
    reap(r.pids)


def sc_health(t: T, shared: Path) -> None:
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200 if self.path == "/healthz" else 404)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):  # noqa: D401
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        r = Repo(shared)
        r.declare({"start": r.start_cmd("one"), "expect": ["api ready"], "health": [base + "/healthz"], "timeout_s": 20})
        res = r.smoke()
        t.check("a health URL that answers 2xx passes", res.code == 0, res.text)
        r = Repo(shared)
        r.declare({"start": r.start_cmd("one"), "expect": ["api ready"], "health": [base + "/missing"], "timeout_s": 3})
        res = r.smoke()
        t.eq("a health URL that answers 404 fails by timeout", res.code, 4)
        t.has("... and is named", res.err, "/missing")
    finally:
        srv.shutdown()


def sc_declaration(t: T, shared: Path) -> None:
    r = Repo(shared)
    t.eq("no smoke.json and no --start: exit 2, never a silent pass", r.smoke().code, 2)
    r.declare({"start": "", "expect": []})
    res = r.smoke()
    t.eq("an empty start: nothing to check, exit 0", res.code, 0)
    t.has("... and it says so", res.out, "no packaged program declared")
    r.declare({"start": r.start_cmd("one"), "expect": []})
    res = r.smoke()
    t.eq("a start with nothing expected: exit 2", res.code, 2)
    t.has("... says what to list", res.err, "readiness line")
    r.declare({"start": r.start_cmd("one"), "expect": ["api ready"], "timeout_s": 0})
    t.eq("a timeout of 0: exit 2", r.smoke().code, 2)
    (r.root / "scripts/delivery/smoke.json").write_text("{not json", encoding="utf-8")
    t.eq("a declaration that is not JSON: exit 2", r.smoke().code, 2)
    (r.root / "scripts/delivery/smoke.json").write_text("{}", encoding="utf-8")
    t.eq("a declaration without a smoke object: exit 2", r.smoke().code, 2)


def sc_templates(t: T, shared: Path) -> None:
    for track in TRACKS:
        base = tdg.TOOLING / track
        smoke = base / "scripts/delivery/smoke.json"
        t.check("%s: has a smoke.json template" % track, smoke.exists())
        if smoke.exists():
            data = json.loads(smoke.read_text(encoding="utf-8")).get("smoke", {})
            t.check("%s: smoke.json has start, expect, timeout_s" % track,
                    all(k in data for k in ("start", "expect", "timeout_s")), str(data))
        wf = base / ".github/workflows/package.yml"
        t.check("%s: has a package.yml workflow" % track, wf.exists())
        if not wf.exists():
            continue
        text = wf.read_text(encoding="utf-8")
        t.check("%s: package.yml is started by hand too" % track, "workflow_dispatch:" in text)
        t.check("%s: package.yml is path-filtered" % track, re.search(r"^\s+paths:\s*$", text, re.M) is not None)
        t.check("%s: package.yml never runs for docs only" % track, "'!docs/**'" in text and "'!**/*.md'" in text)
        t.check("%s: package.yml runs the packaged-program smoke test" % track, "scripts/delivery/smoke_packaged.py" in text)
        t.check("%s: package.yml skips drafts" % track, "pull_request.draft" in text)
        t.check("%s: package.yml reads the runner from CI_RUNS_ON" % track, "fromJSON(vars.CI_RUNS_ON || '\"ubuntu-latest\"')" in text)
        if "upload-artifact" in text:
            t.check("%s: the artifact has a stable name" % track, re.search(r"name:\s*packaged-program\s*$", text, re.M) is not None)
    prune = (shared / ".github/workflows/artifact-prune.yml").read_text(encoding="utf-8")
    t.check("artifact-prune.yml watches the Package workflow", '"Package"' in prune)


MUTANTS = [
    ("a missing worker line passes", S, "for want in [w for w in waiting if w in line]:", "for want in list(waiting):", "workers"),
    ("the process tree is left running", S, "        stop_tree(proc)\n", "        pass\n", "stop_tree"),
    ("a program that exits is a pass", S, "return dc.EXIT_FAIL if exited else dc.EXIT_TIMEOUT", "return dc.EXIT_OK", "workers"),
    ("an unreachable health URL counts as healthy", S, "ValueError):\n        return False", "ValueError):\n        return True", "health"),
    ("a start with nothing expected is accepted", S, "if start.strip() and not expect and not health:", "if False:", "declaration"),
    ("a missing declaration passes", S, "if args.config or not args.start:", "if args.config:", "declaration"),
]

SCENARIOS = {
    "workers": sc_workers,
    "stop_tree": sc_stop_tree,
    "health": sc_health,
    "declaration": sc_declaration,
    "templates": sc_templates,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-mutants", action="store_true", help="skip the mutation pass")
    ap.add_argument("-k", metavar="SUBSTRING", help="run only scenarios/mutants whose name contains it")
    args = ap.parse_args()

    fails = total = 0
    for name, fn in SCENARIOS.items():
        if args.k and args.k not in name:
            continue
        t = T(name)
        try:
            fn(t, SHARED)
        except Exception:  # noqa: BLE001
            t.check("scenario ran to the end", False, traceback.format_exc())
        total += t.total
        fails += len(t.failures)

    if not args.no_mutants:
        print("\n--- mutation pass: break one rule in a copy; the scenario for it must fail ---")
        for label, rel, old, new, scenario in MUTANTS:
            if args.k and args.k not in scenario and args.k not in label:
                continue
            shared = tdg.mutated_shared(rel, old, new)
            total += 1
            if shared is None:
                fails += 1
                print("FAIL  mutant '%s': the text to mutate is not (uniquely) in %s; update the test" % (label, rel))
                continue
            t = T(scenario, quiet=True)
            crashed = False
            try:
                SCENARIOS[scenario](t, shared)
            except tdg.MutantStop:
                pass
            except Exception:  # noqa: BLE001
                crashed = True
            caught = bool(t.failures) or crashed
            print("%s  mutant '%s': %s" % (
                "PASS" if caught else "FAIL", label,
                ("caught by %d check(s)%s" % (len(t.failures), " + a crash" if crashed else "")) if caught
                else "NOT CAUGHT; scenario '%s' cannot fail on this rule" % scenario))
            fails += not caught

    print("\n%d checks, %d failed" % (total, fails))
    for tmp in (_TMP, tdg._TMP_ROOT):
        try:
            tdg.rmtree(tmp)
        except OSError:
            pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
