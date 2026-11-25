#!/usr/bin/env python3
"""One-command onboarding in warn mode (R5.73, DP10, owner decision D10).

    delivery_onboard.py --merge-mode auto|manual [--root DIR]

For a project with no `.delivery/config.json`. Writes `.delivery/config.json` from the plugin template with
`enforcement.mode` "warn" (nothing is ever blocked; the hooks only say what they would have blocked) and the
`watcher.merge_mode` the owner chose, and `.delivery/ledger.json` from the template when it is missing.
There is no default merge mode: the command refuses without `--merge-mode`.
An existing config is never touched (exit 1). It never commits or pushes. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(PLUGIN, "templates", "shared", ".delivery")


def _load(name):
    with open(os.path.join(TEMPLATE, name), encoding="utf-8") as f:
        return json.load(f)


def onboard(root, merge_mode):
    """Write the warn-mode config and the empty ledger under `root`. Returns the list of files written."""
    if merge_mode not in ("auto", "manual"):
        raise ValueError("merge_mode must be auto or manual")
    d = os.path.join(root, ".delivery")
    cfg_path = os.path.join(d, "config.json")
    if os.path.exists(cfg_path):
        raise FileExistsError("%s exists; onboarding never changes an existing config" % cfg_path)
    cfg = {k: v for k, v in _load("config.json").items() if not k.startswith("_")}
    cfg["enforcement"] = dict(cfg.get("enforcement") or {}, mode="warn")
    cfg["watcher"] = dict(cfg.get("watcher") or {}, merge_mode=merge_mode)
    os.makedirs(d, exist_ok=True)
    written = [cfg_path]
    with open(cfg_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    led_path = os.path.join(d, "ledger.json")
    if not os.path.exists(led_path):
        with open(led_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(_load("ledger.json"), f, indent=2)
            f.write("\n")
        written.append(led_path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description="Turn on the delivery rules in warn mode for a project with none.")
    ap.add_argument("--merge-mode", choices=["auto", "manual"], required=False,
                    help="auto: merge on green; manual: the owner merges (no default)")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    if not a.merge_mode:
        print("delivery_onboard: --merge-mode is required: auto (merge on green) or manual (the owner merges)",
              file=sys.stderr)
        return 2
    try:
        files = onboard(a.root, a.merge_mode)
    except FileExistsError as exc:
        print("delivery_onboard: %s" % exc, file=sys.stderr)
        return 1
    for p in files:
        print("wrote %s" % p)
    print("Warn mode is on: nothing is blocked. See what would have been: delivery_report.py. "
          "Switch to blocking by setting enforcement.mode to block.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
