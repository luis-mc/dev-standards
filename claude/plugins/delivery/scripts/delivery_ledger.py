#!/usr/bin/env python3
"""Delivery ledger: .delivery/ledger.json (DELIVERYSPEC section 2).

One file per repository, written only through this module: a lock file, a write to a
temp file in the same folder and an atomic rename. `phases.actual` of a train is derived
from its timestamps and never typed. `events` keeps the last 500 entries.

Module use (best effort for callers, see `record`):
    import delivery_ledger as L
    L.update(root, lambda led: ...)
CLI:
    delivery_ledger.py plan --branch release/29 --release-no 29 --cargo CO148:CO148-fix:409
    delivery_ledger.py hold --train T-... --reason "owner asked" [--until ISO] [--release]
    delivery_ledger.py measure --train T-... --state clean|regressions|none [--report path]
    delivery_ledger.py show [--json]

Standard library only. Config: .delivery/config.json (tz, base, ...).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
EVENT_CAP = 500
DEFAULT_TZ = "Europe/Lisbon"
LOCK_STALE_SECONDS = 30
LOCK_WAIT_SECONDS = 10
DIR_NAME = ".delivery"
TRAIN_STATES = ("planned", "joining", "joined", "pushed", "ci", "green", "red", "merged",
                "live", "cleaned", "abandoned")


class LedgerError(Exception):
    pass


# --- paths, time, config ---------------------------------------------------------------

def find_root(start: str | os.PathLike | None = None) -> Path | None:
    """The nearest folder up from `start` holding .delivery/ (or .git), else None."""
    p = Path(start or os.getcwd()).resolve()
    for cand in [p, *p.parents]:
        if (cand / DIR_NAME).is_dir():
            return cand
    for cand in [p, *p.parents]:
        if (cand / ".git").exists():
            return cand
    return None


def ledger_path(root) -> Path:
    return Path(root) / DIR_NAME / "ledger.json"


def config_path(root) -> Path:
    return Path(root) / DIR_NAME / "config.json"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_config(root) -> dict:
    try:
        data = json.loads(config_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def owner_tz(root=None, cfg: dict | None = None):
    name = (cfg if cfg is not None else (load_config(root) if root else {})).get("tz") or DEFAULT_TZ
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - no tzdata: UTC is the honest fallback
        return timezone.utc


def local_iso(text, root=None, cfg=None) -> str:
    dt = parse_iso(text)
    return dt.astimezone(owner_tz(root, cfg)).strftime("%Y-%m-%d %H:%M %Z") if dt else ""


# --- load, lock, atomic write ----------------------------------------------------------

def empty_ledger() -> dict:
    return {"schema": SCHEMA, "updated_at": iso(), "config_ref": ".delivery/config.json",
            "trains": [], "agents": [], "jobs": [], "installs": [], "publishes": [],
            "runners": [], "watchers": [], "owner_questions": [], "events": []}


def load(root) -> dict:
    """The ledger, or an empty one when absent or unreadable (a broken file is never fatal)."""
    try:
        data = json.loads(ledger_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty_ledger()
    if not isinstance(data, dict):
        return empty_ledger()
    base = empty_ledger()
    for key, value in base.items():
        data.setdefault(key, value)
    return data


@contextlib.contextmanager
def locked(root, wait: float = LOCK_WAIT_SECONDS, stale: float = LOCK_STALE_SECONDS):
    """Exclusive lock through a lock file created with O_EXCL; a stale one is broken."""
    path = ledger_path(root).with_suffix(".json.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    fd = None
    while fd is None:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > stale:
                    path.unlink()
                    continue
            except OSError:
                continue
            if time.monotonic() >= deadline:
                raise LedgerError("ledger lock busy: %s" % path)
            time.sleep(0.02)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            path.unlink()


def write_atomic(root, data: dict) -> None:
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="ledger.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def update(root, fn, **lock_kw) -> dict:
    """Lock, load, apply fn(ledger), derive phases, cap events, write. Returns the ledger."""
    with locked(root, **lock_kw):
        led = load(root)
        fn(led)
        for train in led.get("trains", []):
            derive_phases(train)
        led["events"] = led.get("events", [])[-EVENT_CAP:]
        led["schema"] = SCHEMA
        led["updated_at"] = iso()
        write_atomic(root, led)
        return led


def add_event(led: dict, kind: str, ref: str = "", by: str = "ledger", at: str | None = None) -> None:
    led.setdefault("events", []).append({"at": at or iso(), "kind": kind, "ref": ref, "by": by})
    led["events"] = led["events"][-EVENT_CAP:]


# --- phases ----------------------------------------------------------------------------

# name, start field, end field. A gap between two phases is implied, never a phase (DL-17).
PHASE_RULES = (
    ("join", "created_at", "joined_at"),
    ("ci", "pushed_at", "green_at"),
    ("merge", "green_at", "merged_at"),
    ("deploy", "merged_at", "live_at"),
    ("smoke", "live_at", "smoke.at"),
    ("clean", "live_at", "cleaned_at"),
)


def _field(train: dict, dotted: str):
    cur = train
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def derive_phases(train: dict) -> list[dict]:
    """Fill train['phases']['actual'] from timestamps: a phase exists once both ends do and
    end >= start. `clean` is not a spec phase name, so it is left out of the list."""
    actual = []
    for name, start_f, end_f in PHASE_RULES:
        if name == "clean":
            continue
        start, end = _field(train, start_f), _field(train, end_f)
        s, e = parse_iso(start), parse_iso(end)
        if s and e and e >= s:
            actual.append({"name": name, "start": start, "end": end})
    phases = train.setdefault("phases", {})
    phases.setdefault("planned", [])
    phases["actual"] = actual
    return actual


# --- trains ----------------------------------------------------------------------------

def new_train(led: dict, branch: str, release_no=None, cargo=None, cfg=None, planned=None,
              now: datetime | None = None) -> dict:
    now = now or utcnow()
    day = now.astimezone(owner_tz(cfg=cfg or {})).strftime("%Y-%m-%d")
    prefix = "T-%s-" % day
    taken = [t["id"] for t in led["trains"] if str(t.get("id", "")).startswith(prefix)]
    train = {
        "id": "%s%02d" % (prefix, len(taken) + 1),
        "release_no": release_no, "branch": branch, "pr": None, "state": "planned",
        "hold": None, "cargo": cargo or [],
        "phases": {"planned": planned or [], "actual": []},
        "ci": {"head_sha": None, "run_ids": [], "state": "queued", "started_at": None},
        "measure": {"state": "none", "at": None, "report": None},
        "smoke": {"state": None, "at": None},
        "created_at": iso(now), "joined_at": None, "pushed_at": None, "green_at": None,
        "merged_at": None, "live_at": None, "cleaned_at": None,
    }
    led["trains"].append(train)
    add_event(led, "train.plan", train["id"], "delivery_ledger")
    return train


def find_train(led: dict, key=None, *, pr=None, branch=None) -> dict | None:
    for t in led.get("trains", []):
        if key and t.get("id") == key:
            return t
        if pr is not None and t.get("pr") == pr:
            return t
        if branch and t.get("branch") == branch:
            return t
    return None


def set_train_state(train: dict, state: str, at: str | None = None) -> None:
    """Move a train to `state` and stamp the matching timestamp (first stamp wins)."""
    at = at or iso()
    train["state"] = state
    stamp = {"joined": "joined_at", "pushed": "pushed_at", "green": "green_at",
             "merged": "merged_at", "live": "live_at", "cleaned": "cleaned_at"}.get(state)
    if stamp and not train.get(stamp):
        train[stamp] = at


def hold_active(train: dict, now: datetime | None = None) -> bool:
    hold = train.get("hold")
    if not hold:
        return False
    until = parse_iso(hold.get("until")) if isinstance(hold, dict) else None
    return not (until and until <= (now or utcnow()))


# --- generic best-effort entry point for other scripts ---------------------------------

def record(root, op: str, **kw) -> bool:
    """Best effort: apply a named write; never raises, returns whether it wrote.

    ops: train_state(train|pr|branch, state, **fields), cargo(train|branch, task, **fields),
         ci(train|pr|branch, sha, state), runners(rows), event(kind, ref, by),
         job(fields) and runner(fields): upsert one `jobs[]` row by id / one `runners[]` row by name.
    """
    try:
        if root is None or not Path(root).is_dir():
            return False

        def fn(led):
            by = kw.get("by", "script")
            if op == "event":
                add_event(led, kw.get("kind", "event"), kw.get("ref", ""), by)
                return
            if op in ("job", "runner"):
                key, rows = ("id", led.setdefault("jobs", [])) if op == "job" else ("name", led.setdefault("runners", []))
                fields = dict(kw.get("fields") or {})
                row = next((r for r in rows if r.get(key) == fields.get(key)), None)
                if row is None:
                    row = {}
                    rows.append(row)
                row.update(fields)
                return
            if op == "runners":
                led["runners"] = list(kw.get("rows", []))
                add_event(led, "runners.checked", "%d" % len(led["runners"]), by)
                return
            train = find_train(led, kw.get("train"), pr=kw.get("pr"), branch=kw.get("branch"))
            if train is None and op == "ci" and kw.get("sha"):
                sha = str(kw["sha"])[:7]
                train = next((t for t in led["trains"] if str((t.get("ci") or {}).get("head_sha") or "").startswith(sha)), None) \
                    or next((t for t in led["trains"] if t.get("state") in ("pushed", "ci")), None)
            if train is None:
                add_event(led, "%s.unmatched" % op, str(kw.get("train") or kw.get("pr") or kw.get("branch")), by)
                return
            if op == "train_state":
                for k, v in (kw.get("fields") or {}).items():
                    train[k] = v
                if kw.get("state"):
                    set_train_state(train, kw["state"])
                add_event(led, "train.%s" % train["state"], train["id"], by)
            elif op == "cargo":
                row = next((c for c in train["cargo"] if c.get("task") == kw.get("task")), None)
                if row is None:
                    row = {"task": kw.get("task")}
                    train["cargo"].append(row)
                row.update(kw.get("fields") or {})
                add_event(led, "cargo.%s" % kw.get("task"), train["id"], by)
            elif op == "ci":
                train["ci"].update({"head_sha": kw.get("sha"), "state": kw.get("state")})
                if kw.get("state") == "success":
                    set_train_state(train, "green")
                elif kw.get("state") == "failure":
                    set_train_state(train, "red")
                add_event(led, "ci.%s" % kw.get("state"), train["id"], by)

        update(root, fn)
        return True
    except Exception:  # noqa: BLE001 - recording must never break the caller
        return False


# --- CLI ---------------------------------------------------------------------------------

def _cmd_plan(root, args) -> int:
    cfg = load_config(root)
    cargo = []
    for spec in args.cargo or []:
        parts = spec.split(":")
        row = {"task": parts[0], "branch": parts[1] if len(parts) > 1 else None,
               "pr": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
               "sha": None, "gate": "none", "joined_sha": None, "paths": []}
        cargo.append(row)
    planned = []
    for spec in args.phase or []:  # name=minutes
        name, _, mins = spec.partition("=")
        if mins.isdigit():
            planned.append({"name": name, "minutes": int(mins), "basis": "plan"})
    out = {}

    def fn(led):
        out["train"] = new_train(led, args.branch, args.release_no, cargo, cfg, planned)
    update(root, fn)
    print(out["train"]["id"])
    return 0


def _cmd_hold(root, args) -> int:
    def fn(led):
        t = find_train(led, args.train)
        if t is None:
            raise LedgerError("no train %s" % args.train)
        if args.release:
            t["hold"] = None
            add_event(led, "hold.release", t["id"], "owner")
        else:
            if not args.reason:
                raise LedgerError("a hold needs --reason (the owner's reason)")
            t["hold"] = {"reason": args.reason, "by": args.by, "until": args.until}
            add_event(led, "hold.set", t["id"], args.by)
    update(root, fn)
    return 0


def _cmd_measure(root, args) -> int:
    def fn(led):
        t = find_train(led, args.train)
        if t is None:
            raise LedgerError("no train %s" % args.train)
        t["measure"] = {"state": args.state, "at": iso(), "report": args.report}
        add_event(led, "measure.%s" % args.state, t["id"], "measure")
    update(root, fn)
    return 0


def _cmd_show(root, args) -> int:
    led = load(root)
    if args.json:
        print(json.dumps(led, indent=2, ensure_ascii=False))
        return 0
    cfg = load_config(root)
    print("ledger updated %s" % local_iso(led.get("updated_at"), cfg=cfg))
    for t in led["trains"]:
        hold = " HOLD(%s)" % t["hold"].get("reason") if t.get("hold") else ""
        print("train %s %s pr=%s state=%s ci=%s%s" % (t["id"], t.get("branch"), t.get("pr"), t.get("state"),
                                                       (t.get("ci") or {}).get("state"), hold))
        for ph in t.get("phases", {}).get("actual", []):
            print("  %-7s %s -> %s" % (ph["name"], local_iso(ph["start"], cfg=cfg), local_iso(ph["end"], cfg=cfg)))
    for a in led["agents"]:
        print("agent %s %s state=%s" % (a.get("task"), a.get("branch"), a.get("state")))
    open_q = [q for q in led["owner_questions"] if not q.get("answered_at")]
    print("owner questions open: %d; events: %d" % (len(open_q), len(led["events"])))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", help="repository root (default: nearest folder with .delivery/ or .git)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--branch", required=True)
    p.add_argument("--release-no", type=int)
    p.add_argument("--cargo", action="append", metavar="TASK[:BRANCH[:PR]]")
    p.add_argument("--phase", action="append", metavar="NAME=MINUTES")
    p = sub.add_parser("hold")
    p.add_argument("--train", required=True)
    p.add_argument("--reason")
    p.add_argument("--by", default="owner", choices=("owner", "rule"))
    p.add_argument("--until")
    p.add_argument("--release", action="store_true")
    p = sub.add_parser("measure")
    p.add_argument("--train", required=True)
    p.add_argument("--state", required=True, choices=("none", "clean", "regressions"))
    p.add_argument("--report")
    p = sub.add_parser("show")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root) if args.root else find_root()
    if root is None:
        print("delivery_ledger: no repository root found", file=sys.stderr)
        return 2
    try:
        return {"plan": _cmd_plan, "hold": _cmd_hold, "measure": _cmd_measure, "show": _cmd_show}[args.cmd](root, args)
    except LedgerError as exc:
        print("delivery_ledger: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
