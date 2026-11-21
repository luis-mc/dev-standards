#!/usr/bin/env python3
"""Lifecycle contract tools (DS235a, DOCSPEC R15.13 to R15.15).

  lifecycle_check.py validate FILE            LC-1: check a lifecycle.json against schemas/lifecycle.schema.json
  lifecycle_check.py setup --root DIR --local-app yes|no [--apply]
                                              write docs/design-system/next-version/lifecycle.json (and words.json)
                                              from the starter, only for a project with a local app; never overwrites

Standard library only. `validate()` is a small JSON Schema reader (type, enum, const, required, properties,
additionalProperties, items, minItems, maxItems, minLength, minProperties, pattern), enough for the schema here.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SCHEMA = PLUGIN / "schemas" / "lifecycle.schema.json"
STARTER = PLUGIN / "templates" / "design-system" / "lifecycle"
DEFAULT_BANNED = ["OK", "Yes", "No", "Install now", "Later", "daemon", "binary", "payload"]
CASE_SENSITIVE = {"OK", "Yes", "No", "Later"}

_TYPES = {"object": dict, "array": list, "string": str, "number": (int, float), "null": type(None), "boolean": bool}


def _type_ok(v, t):
    ts = t if isinstance(t, list) else [t]
    return any(isinstance(v, _TYPES[x]) and not (x == "number" and isinstance(v, bool)) for x in ts)


def _check(v, s, at, out):
    if "const" in s and v != s["const"]:
        out.append(f"{at}: must be {s['const']!r}")
    if "enum" in s and v not in s["enum"]:
        out.append(f"{at}: {v!r} is not one of {s['enum']}")
    if "type" in s and not _type_ok(v, s["type"]):
        out.append(f"{at}: wrong type")
        return
    if isinstance(v, str):
        if len(v) < s.get("minLength", 0):
            out.append(f"{at}: empty")
        if "pattern" in s and not re.search(s["pattern"], v):
            out.append(f"{at}: {v!r} does not match {s['pattern']}")
    if isinstance(v, list):
        if len(v) < s.get("minItems", 0):
            out.append(f"{at}: needs at least {s['minItems']} item(s)")
        if len(v) > s.get("maxItems", 1 << 30):
            out.append(f"{at}: at most {s['maxItems']} item(s)")
        for i, x in enumerate(v):
            _check(x, s.get("items", {}), f"{at}[{i}]", out)
    if isinstance(v, dict):
        if len(v) < s.get("minProperties", 0):
            out.append(f"{at}: needs at least {s['minProperties']} key(s)")
        for k in s.get("required", []):
            if k not in v:
                out.append(f"{at}: missing '{k}'")
        props = s.get("properties", {})
        for k, x in v.items():
            if k in props:
                _check(x, props[k], f"{at}.{k}", out)
            elif isinstance(s.get("additionalProperties"), dict):
                _check(x, s["additionalProperties"], f"{at}.{k}", out)
            elif s.get("additionalProperties") is False:
                out.append(f"{at}: unknown key '{k}'")


def banned_in(text, banned):
    return [w for w in banned if re.search(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text, 0 if w in CASE_SENSITIVE else re.I)]


def validate(doc):
    """Problems of a lifecycle document (empty list: valid). LC-1."""
    out = []
    _check(doc, json.loads(SCHEMA.read_text(encoding="utf-8")), "$", out)
    if out or not isinstance(doc, dict):
        return out
    for name, flow in doc["flows"].items():
        known = set(flow["states"])
        for i, t in enumerate(flow["transitions"]):
            for end in ("from", "to"):
                if t[end] not in known:
                    out.append(f"$.flows.{name}.transitions[{i}].{end}: '{t[end]}' is not a state of this flow")
    banned = list(dict.fromkeys(DEFAULT_BANNED + doc["words"]["banned"]))
    for state, items in doc["words"]["states"].items():
        for key, text in items.items():
            for w in banned_in(text, banned):
                out.append(f"$.words.states.{state}.{key}: banned word '{w}'")
    return out


def setup(root, local_app, apply=False):
    """Write the starter lifecycle.json and words.json into next-version, only for a local-app project."""
    if not local_app:
        return "skipped: no local app"
    dest = Path(root) / "docs" / "design-system" / "next-version"
    if not dest.is_dir():
        return "failed: docs/design-system/next-version does not exist; run design_system.py init first"
    todo = [f for f in ("lifecycle.json", "words.json") if not (dest / f).exists()]
    if not todo:
        return "nothing to do: lifecycle.json and words.json exist"
    if apply:
        for f in todo:
            shutil.copyfile(STARTER / f, dest / f)
    return ("wrote: " if apply else "would write: ") + ", ".join(f"docs/design-system/next-version/{f}" for f in todo)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("file")
    s = sub.add_parser("setup")
    s.add_argument("--root", default=".")
    s.add_argument("--local-app", choices=["yes", "no"], required=True)
    s.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        problems = validate(json.loads(Path(a.file).read_text(encoding="utf-8")))
        for p in problems:
            print(f"LC-1 {p}")
        print("ok" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    msg = setup(a.root, a.local_app == "yes", a.apply)
    print(msg)
    return 1 if msg.startswith("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
