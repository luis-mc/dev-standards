#!/usr/bin/env python3
"""Show or change where CI runs, per OS (DL15). Writes `ci.options` in .delivery/config.json.

    delivery_ci.py show  [--root DIR] [--json]
    delivery_ci.py set   --os linux|windows|macos|all --option a|b|c [--root DIR]
    delivery_ci.py unset --os linux|windows|macos|all [--root DIR]

Options: a = self-hosted (GitHub Actions on the owner's runners), b = github-hosted (GitHub Actions on GitHub's
runners), c = cloud (Claude cloud sessions, no Actions, no webhooks). The long names work too.

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


def normalise_option(raw: str):
    raw = (raw or "").strip().lower()
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
    return [{"os": o, "option": opts.get(o), "letter": C.CI_OPTION_LETTER.get(opts.get(o))} for o in C.CI_OS]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_ci.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=["show", "set", "unset"])
    ap.add_argument("--os", dest="os_name", help="linux, windows, macos or all")
    ap.add_argument("--option", help="a, b or c (self-hosted, github-hosted, cloud)")
    ap.add_argument("--root", default=".", help="repository root (default: the current folder)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
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
                print("%-8s %s" % (r["os"], "%s (%s)" % (r["option"], r["letter"]) if r["option"] else "not chosen"))
        return 0
    if args.os_name not in (*C.CI_OS, "all"):
        print("delivery_ci: --os must be linux, windows, macos or all", file=sys.stderr)
        return 1
    oses = list(C.CI_OS) if args.os_name == "all" else [args.os_name]
    option = None
    if args.action == "set":
        option = normalise_option(args.option)
        if option is None:
            print("delivery_ci: --option must be a, b or c (self-hosted, github-hosted, cloud)", file=sys.stderr)
            return 1
    write_config(path, change(cfg, oses, option))
    for r in describe(read_config(path)):
        if r["os"] in oses:
            print("%-8s %s" % (r["os"], r["option"] or "not chosen"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
