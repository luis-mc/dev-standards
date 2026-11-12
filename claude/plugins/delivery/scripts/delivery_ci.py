#!/usr/bin/env python3
"""Show or change where CI runs, per OS (DL15). Writes `ci.options` in .delivery/config.json.

    delivery_ci.py show  [--root DIR] [--json]
    delivery_ci.py set   --os linux|windows|macos|all --option 1|2|3 [--root DIR]
    delivery_ci.py unset --os linux|windows|macos|all [--root DIR]
    delivery_ci.py add-runner --os linux|windows|macos [--labels a,b] [--root DIR]
    delivery_ci.py slots [--json]

Option 1 = self-hosted (GitHub Actions on your own self-hosted runners, on any machines you run), Option 2 =
github-hosted (GitHub Actions on GitHub's runners), Option 3 = cloud (Claude cloud sessions, no Actions, no
webhooks). The config names work too, and so do the old letters a, b, c. Option 4 (own runners first, a fallback
after a wait) is the `ci.fallback` block; `set` does not turn it on yet.

`slots` (DL-90) prints who holds each CI slot of this machine, the queue, and the wait of each ticket. It needs no
project: the machine folder is read (machine_slots.py).

`add-runner` prints the by-hand steps to add one more runner of a label on another machine. A job that waits
more than X minutes for a runner means: add a runner with that label on another machine.

There is no default. An OS that is not set is "not chosen"; setup must ask the owner, and `delivery_doctor.py`
fails for a shard whose OS is not chosen. The command changes the config only. It does not touch workflow
files, runners or routines: the doctor says what the new choice still needs.
Exit 0 done, 1 refused (bad value), 2 no .delivery/ folder or unreadable config. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import delivery_config as C  # noqa: E402

LETTERS = {"a": "self-hosted", "b": "github-hosted", "c": "cloud"}


NUMBERS = {"1": "self-hosted", "2": "github-hosted", "3": "cloud"}


def normalise_option(raw: str):
    raw = (raw or "").strip().lower()
    if raw.startswith("option"):
        raw = raw[6:].strip()
    if raw in NUMBERS:
        return NUMBERS[raw]
    if raw in LETTERS:
        return LETTERS[raw]
    return raw if raw in C.CI_OPTIONS else None


def read_config(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("config is not a JSON object")
    return data


def write_config(path: str, cfg: dict) -> None:
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def change(cfg: dict, oses: list, option) -> dict:
    ci = cfg.get("ci") if isinstance(cfg.get("ci"), dict) else {}
    opts = ci.get("options") if isinstance(ci.get("options"), dict) else {}
    for o in oses:
        if option is None:
            opts.pop(o, None)
        else:
            opts[o] = option
    ci["options"] = opts
    cfg["ci"] = ci
    return cfg


def describe(cfg: dict) -> list:
    opts = C.ci_options(cfg)
    return [{"os": o, "option": opts.get(o), "letter": C.CI_OPTION_LETTER.get(opts.get(o)),
             "number": C.CI_OPTION_NUMBER.get(opts.get(o))} for o in C.CI_OS]


def _mins(seconds) -> str:
    return "%d min %02d s" % (seconds // 60, seconds % 60)


def print_slots(as_json: bool) -> int:
    import machine_slots as MS
    st = MS.status()
    if as_json:
        print(json.dumps(st))
        return 0
    print("machine folder: %s" % MS.machine_dir())
    for s in st["slots"]:
        if s["free"]:
            print("slot %d  free" % s["slot"])
        else:
            print("slot %d  %s run %s job %s%s  runner %s  held %s%s" % (
                s["slot"], s.get("repo"), s.get("run_id"), s.get("job"),
                " (%s)" % s["shard"] if s.get("shard") else "", s.get("runner"), _mins(s["age_s"]),
                "  STALE" if s.get("stale") else ""))
    for s in st.get("light_slots", []):
        if s["free"]:
            print("light %d  free" % s["slot"])
        else:
            print("light %d  %s run %s job %s%s  runner %s  held %s%s" % (
                s["slot"], s.get("repo"), s.get("run_id"), s.get("job"),
                " (%s)" % s["shard"] if s.get("shard") else "", s.get("runner"), _mins(s["age_s"]),
                "  STALE" if s.get("stale") else ""))
    if not st["queue"]:
        print("queue   empty")
    for i, t in enumerate(st["queue"], 1):
        print("queue %d  %s run %s job %s%s  priority %s  waiting %s" % (
            i, t.get("repo"), t.get("run_id"), t.get("job"), " (%s)" % t["shard"] if t.get("shard") else "",
            "first (ready PR or default branch)" if t.get("priority") == 0 else "normal", _mins(t["wait_s"])))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_ci.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["show", "set", "unset", "add-runner", "slots"])
    ap.add_argument("--os", dest="os_name", help="linux, windows, macos or all")
    ap.add_argument("--option", help="1, 2 or 3 (self-hosted, github-hosted, cloud)")
    ap.add_argument("--labels", help="add-runner: the labels of the runner, comma separated")
    ap.add_argument("--root", default=".", help="repository root (default: the current folder)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.action == "slots":
        return print_slots(args.json)
    if args.action == "add-runner":
        if args.os_name not in C.CI_OS:
            print("delivery_ci: --os must be linux, windows or macos", file=sys.stderr)
            return 1
        labels = [x.strip() for x in (args.labels or "").split(",") if x.strip()]
        print("Add a runner on another machine (%s), by hand:" % args.os_name)
        for i, step in enumerate(C.runner_steps(args.os_name, labels), 1):
            print("%d. %s" % (i, step))
        print(C.add_runner_advice())
        return 0
    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, ".delivery")):
        print("delivery_ci: no .delivery/ folder in %s" % root, file=sys.stderr)
        return 2
    path = C.config_file(root)
    try:
        cfg = read_config(path)
    except (OSError, ValueError) as exc:
        print("delivery_ci: cannot read %s (%s)" % (path, exc), file=sys.stderr)
        return 2
    if args.action == "show":
        rows = describe(cfg)
        if args.json:
            print(json.dumps(rows))
        else:
            for r in rows:
                print("%-8s %s" % (r["os"], C.option_name(r["option"]) or "not chosen"))
        return 0
    if args.os_name not in (*C.CI_OS, "all"):
        print("delivery_ci: --os must be linux, windows, macos or all", file=sys.stderr)
        return 1
    oses = list(C.CI_OS) if args.os_name == "all" else [args.os_name]
    option = None
    if args.action == "set":
        option = normalise_option(args.option)
        if option is None:
            print("delivery_ci: --option must be 1, 2 or 3 (self-hosted, github-hosted, cloud). "
                  "Option 4 (own runners, then a fallback) is not built yet", file=sys.stderr)
            return 1
    write_config(path, change(cfg, oses, option))
    for r in describe(read_config(path)):
        if r["os"] in oses:
            print("%-8s %s" % (r["os"], C.option_name(r["option"]) or "not chosen"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
