#!/usr/bin/env python3
"""Heavy-job wrapper (DELIVERYSPEC DL-50, DL-51, D6): run one heavy local command without stealing the
CI runners from a release train.

    runner_plan.py run --label NAME [options] -- <command> [args...]

Before the command starts it
  1. waits while any release/train CI run (head branch matching `train_branch_regex`, default `^release/`)
     is queued or running, and logs `runner_plan: waiting for CI <run>` every minute;
  2. takes the one-heavy-job-at-a-time lock (`.delivery/runner-plan.lock`; a dead owner's lock is taken over);
  3. waits until free memory is at least the floor (`min_free_mb`);
  4. optionally stops the local runner service (`pause_service`) for the duration.
It then runs the command (optionally with CPU affinity and a lower priority) and ALWAYS starts the
service again and releases the lock afterwards: in a `finally`, and on SIGINT, SIGTERM and (Windows)
SIGBREAK, which also stop the child.

Settings come from `.delivery/config.json` key `runner_plan` and are overridden by the options:
  min_free_mb (int, 0 = off), pause_service (string, the runner's service name), train_branch_regex,
  poll_seconds (60), max_wait_minutes (0 = wait forever), repo ("OWNER/NAME"; default: the current one),
  affinity (list of CPU numbers), priority ("low" | "below-normal" | "normal").

Every job is recorded in `jobs[]` and a paused runner in `runners[].paused_by` of `.delivery/ledger.json`
by a best-effort call to the delivery plugin's ledger module (`delivery_ledger.py`, found through
DELIVERY_LEDGER, a sibling file, or `claude/plugins/delivery/scripts/`): `record(kind, data, root=...)`
with kind "job" (fields as ledger `jobs[]`) or "runner" (name, paused_by). Absent or failing: no-op.

Exit: the command's exit code; 2 usage error; 4 gave up waiting (`max_wait_minutes`); 130 interrupted.
Python 3.8+, standard library only; `gh` is optional (without it the CI wait is skipped with a warning).
"""
from __future__ import annotations

import argparse
import atexit
import ctypes
import datetime
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

EXIT_USAGE = 2
EXIT_TIMEOUT = 4
EXIT_INTERRUPTED = 130
LOCK_NAME = "runner-plan.lock"
ACTIVE_RUN_STATUSES = ("queued", "in_progress", "waiting", "pending", "requested")
DEFAULTS = {
    "min_free_mb": 0, "pause_service": "", "train_branch_regex": r"^release/", "poll_seconds": 60,
    "max_wait_minutes": 0, "repo": "", "affinity": [], "priority": "normal",
}
GH_TIMEOUT = 30


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print("runner_plan: " + msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- OS and gh calls (all injectable)

def gh_json(args):
    """JSON from `gh`, or None when gh is missing or fails (the CI wait is then skipped)."""
    gh = shutil.which("gh")
    if gh is None:
        return None
    try:
        p = subprocess.run([gh, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=GH_TIMEOUT)
        return json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def free_memory_mb():
    """Available memory in MB, or None when it cannot be read."""
    if os.name == "nt":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("tpage", ctypes.c_ulonglong),
                        ("apage", ctypes.c_ulonglong), ("tvirt", ctypes.c_ulonglong),
                        ("avirt", ctypes.c_ulonglong), ("ext", ctypes.c_ulonglong)]
        st = Status()
        st.length = ctypes.sizeof(Status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.avail // (1024 * 1024))
        except (OSError, AttributeError):
            pass
        return None
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def service_control(action: str, name: str) -> bool:
    """Stop or start a runner service: `sc` on Windows, `systemctl` elsewhere. True when it worked."""
    if action not in ("stop", "start"):
        return False
    argv = ["sc", action, name] if os.name == "nt" else ["systemctl", action, name]
    try:
        p = subprocess.run(argv, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    # sc exits 1056/1062 when the service is already running/stopped: that is the wanted state
    return p.returncode == 0 or (os.name == "nt" and p.returncode in (1056, 1062))


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259         # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def apply_limits(pid: int, affinity, priority: str) -> None:
    """Best effort CPU affinity and priority for the running child."""
    try:
        if os.name == "nt":
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x0200 | 0x0400 | 0x0100, False, pid)   # SET_INFORMATION | QUERY | SET_QUOTA
            if h:
                if affinity:
                    k.SetProcessAffinityMask(h, sum(1 << int(c) for c in affinity))
                cls = {"low": 0x40, "below-normal": 0x4000}.get(priority)   # IDLE / BELOW_NORMAL
                if cls:
                    k.SetPriorityClass(h, cls)
                k.CloseHandle(h)
        else:
            if affinity and hasattr(os, "sched_setaffinity"):
                os.sched_setaffinity(pid, {int(c) for c in affinity})
            nice = {"low": 19, "below-normal": 10}.get(priority)
            if nice is not None:
                os.setpriority(os.PRIO_PROCESS, pid, nice)
    except (OSError, ValueError, AttributeError) as exc:
        log("could not apply the CPU limits (%s)" % exc)


# ---------------------------------------------------------------- ledger (best effort)

def find_ledger_module(root: str):
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.environ.get("DELIVERY_LEDGER", ""), os.path.join(here, "delivery_ledger.py")]
    d = os.path.abspath(root)
    for _ in range(6):
        cands.append(os.path.join(d, "claude", "plugins", "delivery", "scripts", "delivery_ledger.py"))
        d = os.path.dirname(d)
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        cands.append(os.path.join(plugin_root, "scripts", "delivery_ledger.py"))
    for c in cands:
        if c and os.path.isfile(c):
            try:
                spec = importlib.util.spec_from_file_location("delivery_ledger", c)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod if callable(getattr(mod, "record", None)) else None
            except Exception:       # a broken ledger module must never stop a job
                return None
    return None


class Ledger:
    def __init__(self, root: str, module="auto"):
        self.root = root
        self.module = find_ledger_module(root) if module == "auto" else module

    def record(self, kind: str, data: dict) -> None:
        if self.module is None:
            return
        try:
            self.module.record(kind, data, root=self.root)
        except Exception as exc:    # best effort
            log("ledger not updated (%s: %s)" % (type(exc).__name__, exc))


# ---------------------------------------------------------------- the plan

class Interrupted(Exception):
    pass


class GaveUp(Exception):
    pass


class Plan:
    def __init__(self, root, cfg, label, cmd, ledger=None, gh=gh_json, free_mb=free_memory_mb,
                 service=service_control, alive=pid_alive, sleep=time.sleep, clock=time.monotonic,
                 popen=subprocess.Popen, limits=apply_limits):
        self.root, self.cfg, self.label, self.cmd = root, cfg, label, cmd
        self.ledger = ledger if ledger is not None else Ledger(root, None)
        self.gh, self.free_mb, self.service, self.alive = gh, free_mb, service, alive
        self.sleep, self.clock, self.popen, self.limits = sleep, clock, popen, limits
        self.job_id = "%s-%d" % (label, int(time.time()))
        self.lock_path = os.path.join(root, ".delivery", LOCK_NAME)
        self.have_lock = False
        self.paused = False
        self.child = None
        self.interrupted = False
        self.started = None
        self.t0 = self.clock()

    # --- recording
    def job(self, state: str, **extra) -> None:
        data = {"id": self.job_id, "label": self.label, "cmd": " ".join(self.cmd), "heavy": True,
                "pid": self.child.pid if self.child else os.getpid(), "log_path": None,
                "started": self.started or utc_now(), "last_checked": utc_now(), "state": state}
        data.update(extra)
        self.ledger.record("job", data)

    # --- waiting
    def wait_until(self, blocked, describe, state="waiting-ci") -> None:
        """Poll `blocked()` (None when free, else a text) every poll_seconds; log it once a minute."""
        poll = max(1, float(self.cfg["poll_seconds"]))
        limit = float(self.cfg["max_wait_minutes"]) * 60
        last_log = None
        while True:
            if self.interrupted:
                raise Interrupted()
            why = blocked()
            if why is None:
                return
            now = self.clock()
            if last_log is None or now - last_log >= 60:
                log("%s %s" % (describe, why))
                self.job(state)
                last_log = now
            if limit and now - self.t0 >= limit:
                raise GaveUp("gave up waiting after %g minutes (%s %s)" % (limit / 60, describe, why))
            left = poll
            while left > 0 and not self.interrupted:      # slices, so a signal is noticed within a second
                self.sleep(min(1.0, left))
                left -= 1.0

    def ci_blocker(self):
        """Text naming an active release/train CI run, or None. A gh failure never blocks (warned once)."""
        args = ["run", "list", "--limit", "50", "--json", "databaseId,status,headBranch,workflowName,event"]
        if self.cfg["repo"]:
            args += ["--repo", self.cfg["repo"]]
        runs = self.gh(args)
        if not isinstance(runs, list):
            if not getattr(self, "_warned_gh", False):
                log("warning: cannot list CI runs (gh missing or failing); not waiting for CI")
                self._warned_gh = True
            return None
        pattern = re.compile(self.cfg["train_branch_regex"])
        for r in runs:
            if isinstance(r, dict) and r.get("status") in ACTIVE_RUN_STATUSES \
                    and pattern.search(str(r.get("headBranch", ""))):
                return "%s (%s on %s, %s)" % (r.get("databaseId"), r.get("workflowName") or "workflow",
                                              r.get("headBranch"), r.get("status"))
        return None

    def lock_blocker(self):
        """Try to take the lock; text naming the holder when it is held by a live process."""
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder = self.read_lock()
                if holder and self.alive(int(holder.get("pid", 0) or 0)):
                    return "another heavy job (%s, pid %s) is running" % (holder.get("label"), holder.get("pid"))
                try:
                    os.remove(self.lock_path)       # its owner is gone: take it over
                except OSError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "label": self.label, "job": self.job_id, "at": utc_now()}, f)
            self.have_lock = True
            return None
        return "the lock file could not be taken"

    def read_lock(self):
        try:
            with open(self.lock_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def memory_blocker(self):
        floor = int(self.cfg["min_free_mb"] or 0)
        if floor <= 0:
            return None
        free = self.free_mb()
        if free is None:
            return None
        return None if free >= floor else "%d MB free, need %d MB" % (free, floor)

    # --- pausing
    def pause(self) -> None:
        name = self.cfg["pause_service"]
        if not name:
            return
        if self.service("stop", name):
            self.paused = True
            log("paused runner service %s for %s" % (name, self.job_id))
            self.ledger.record("runner", {"name": name, "paused_by": self.job_id, "checked_at": utc_now()})
        else:
            log("warning: could not stop runner service %s; running without pausing it" % name)

    def resume(self) -> None:
        name = self.cfg["pause_service"]
        if not (name and self.paused):
            return
        ok = self.service("start", name)
        for _ in range(2):
            if ok:
                break
            ok = self.service("start", name)
        self.paused = False if ok else self.paused
        log("resumed runner service %s" % name if ok else "ERROR: runner service %s did not restart; start it by hand" % name)
        if ok:
            self.ledger.record("runner", {"name": name, "paused_by": None, "checked_at": utc_now()})

    def release_lock(self) -> None:
        if self.have_lock:
            holder = self.read_lock()
            if holder is None or holder.get("job") == self.job_id:
                try:
                    os.remove(self.lock_path)
                except OSError:
                    pass
            self.have_lock = False

    def cleanup(self) -> None:
        """Idempotent; runs from `finally`, from atexit and from the signal handler."""
        if self.child is not None and self.child.poll() is None:
            try:
                self.child.terminate()
                self.child.wait(timeout=20)
            except Exception:
                try:
                    self.child.kill()
                except Exception:
                    pass
        try:
            self.resume()
        finally:
            self.release_lock()

    def on_signal(self, signum, _frame) -> None:
        self.interrupted = True
        log("signal %s: stopping the job and resuming the runner" % signum)
        if self.child is not None and self.child.poll() is None:
            try:
                self.child.terminate()
            except Exception:
                pass

    # --- run
    def run(self) -> int:
        old = {}
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is not None:
                try:
                    old[sig] = signal.signal(sig, self.on_signal)
                except ValueError:       # not the main thread
                    pass
        atexit.register(self.cleanup)
        code = 1
        try:
            try:
                self.wait_until(self.ci_blocker, "waiting for CI")
                self.wait_until(self.lock_blocker, "waiting for the heavy-job lock:", state="waiting-ci")
                self.wait_until(self.memory_blocker, "waiting for free memory:", state="waiting-ci")
                self.wait_until(self.ci_blocker, "waiting for CI")      # CI may have started while we waited
                self.pause()
                self.started = utc_now()
                kwargs = {}
                if os.name == "nt":
                    kwargs["creationflags"] = {"low": 0x40, "below-normal": 0x4000}.get(self.cfg["priority"], 0)
                self.child = self.popen(self.cmd, **kwargs)
                self.limits(self.child.pid, self.cfg["affinity"], self.cfg["priority"])
                self.job("running")
                code = self.child.wait()
                if self.interrupted:
                    raise Interrupted()
                self.job("done" if code == 0 else "failed", exit_code=code, ended=utc_now())
            except Interrupted:
                code = EXIT_INTERRUPTED
                self.job("failed", exit_code=code, ended=utc_now())
            except GaveUp as exc:
                log(str(exc))
                code = EXIT_TIMEOUT
                self.job("failed", exit_code=code, ended=utc_now())
            except OSError as exc:
                log("cannot start %r: %s" % (self.cmd[0], exc))
                code = EXIT_USAGE
                self.job("failed", exit_code=code, ended=utc_now())
        finally:
            self.cleanup()
            atexit.unregister(self.cleanup)
            for sig, handler in old.items():
                try:
                    signal.signal(sig, handler)
                except ValueError:
                    pass
        return code


# ---------------------------------------------------------------- command line

def load_config(root: str, path: str = "") -> dict:
    cfg = dict(DEFAULTS)
    p = path or os.path.join(root, ".delivery", "config.json")
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        section = data.get("runner_plan") if isinstance(data, dict) else None
        if isinstance(section, dict):
            cfg.update({k: v for k, v in section.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def build_parser():
    ap = argparse.ArgumentParser(prog="runner_plan.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="action", required=True)
    r = sub.add_parser("run", help="run a heavy command: wait for train CI, one at a time, memory floor, pause the runner")
    r.add_argument("--label", required=True, help="name of the job (ledger id prefix)")
    r.add_argument("--root", default=".", help="repository root (holds .delivery/)")
    r.add_argument("--config", default="", help="config file (default .delivery/config.json)")
    r.add_argument("--min-free-mb", type=int)
    r.add_argument("--pause-service")
    r.add_argument("--train-branch-regex")
    r.add_argument("--poll-seconds", type=float)
    r.add_argument("--max-wait-minutes", type=float)
    r.add_argument("--repo")
    r.add_argument("--affinity", help="comma-separated CPU numbers")
    r.add_argument("--priority", choices=("low", "below-normal", "normal"))
    r.add_argument("command", nargs=argparse.REMAINDER, help="-- <command> [args...]")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        log("usage: runner_plan.py run --label NAME -- <command> [args...]")
        return EXIT_USAGE
    root = os.path.abspath(args.root)
    cfg = load_config(root, args.config)
    for opt, key in (("min_free_mb", "min_free_mb"), ("pause_service", "pause_service"),
                     ("train_branch_regex", "train_branch_regex"), ("poll_seconds", "poll_seconds"),
                     ("max_wait_minutes", "max_wait_minutes"), ("repo", "repo"), ("priority", "priority")):
        if getattr(args, opt) is not None:
            cfg[key] = getattr(args, opt)
    if args.affinity:
        try:
            cfg["affinity"] = [int(x) for x in args.affinity.split(",") if x.strip()]
        except ValueError:
            log("--affinity needs comma-separated CPU numbers")
            return EXIT_USAGE
    try:
        re.compile(cfg["train_branch_regex"])
    except re.error as exc:
        log("train_branch_regex is not a regular expression: %s" % exc)
        return EXIT_USAGE
    return Plan(root, cfg, args.label, cmd, ledger=Ledger(root)).run()


if __name__ == "__main__":
    sys.exit(main())
