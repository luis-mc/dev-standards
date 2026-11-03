#!/usr/bin/env python3
"""Config of a delivery project: schema validation and the typed accessors the watcher and hooks use.

    delivery_config.py validate [--root DIR | --config FILE] [--json] [--strict]

Checks `.delivery/config.json` against references/config-schema.json (the JSON Schema subset that file
uses: type, enum, properties, items, minimum, minItems, pattern, oneOf, required, additionalProperties) and
a few things a schema cannot say: regexes compile, the `tz` loads through zoneinfo, no merge flag is --auto.
Exit 0 valid (warnings allowed), 1 errors (or warnings with --strict), 2 the file is missing or not JSON.
Unknown keys are warnings, never errors; keys starting with _ are comments. A missing config is valid
(the defaults apply). Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(os.path.dirname(HERE), "references", "config-schema.json")

ENFORCEMENT_DEFAULTS = {"mode": "block", "block_ceiling": 3, "log_every_block": False}
WATCHER_DEFAULTS = {"push_trains": True, "open_prs": True, "merge_on_green": True, "manage_runners": True}
RUNNER_PLAN_DEFAULTS = {"cancel_replaced_runs": True, "hold_dependabot_during_train": True, "heavy_jobs_yield": True}


# --- accessors (never raise; a bad value falls back to the 0.1.0 behaviour) -------------------------

def _section(cfg, key):
    v = cfg.get(key) if isinstance(cfg, dict) else None
    return v if isinstance(v, dict) else {}


def enforcement(cfg) -> dict:
    e, out = _section(cfg, "enforcement"), dict(ENFORCEMENT_DEFAULTS)
    if e.get("mode") in ("block", "warn"):
        out["mode"] = e["mode"]
    c = e.get("block_ceiling")
    if isinstance(c, int) and not isinstance(c, bool) and c >= 1:
        out["block_ceiling"] = c
    if isinstance(e.get("log_every_block"), bool):
        out["log_every_block"] = e["log_every_block"]
    return out


def _flag(section, names, default):
    for n in names:
        if isinstance(section.get(n), bool):
            return section[n]
    return default


def watcher_flags(cfg) -> dict:
    w = _section(cfg, "watcher")
    return {k: _flag(w, (k,), d) for k, d in WATCHER_DEFAULTS.items()}


def ci_workflows(cfg) -> list:
    """watcher.ci_workflows: the workflow files that must all succeed on the PR head before a train is green."""
    v = _section(cfg, "watcher").get("ci_workflows")
    if isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v):
        return [x.strip() for x in v]
    return ["ci.yml"]


def pr_proven_jobs(cfg) -> list:
    """pr_proven_jobs: job names a release PR proves, which must not re-run on the default branch after the merge."""
    v = cfg.get("pr_proven_jobs") if isinstance(cfg, dict) else None
    return [x.strip() for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def runner_plan_flags(cfg) -> dict:
    r = _section(cfg, "runner_plan")
    return {"cancel_replaced_runs": _flag(r, ("cancel_replaced_runs",), True),
            "hold_dependabot_during_train": _flag(r, ("hold_dependabot_during_train",), True),
            "heavy_jobs_yield": _flag(r, ("heavy_jobs_yield", "heavy_local_jobs_yield"), True)}


# --- CI options (DL15) -----------------------------------------------------------------------------

CI_OS = ("linux", "windows", "macos")
CI_OPTIONS = ("self-hosted", "github-hosted", "cloud")
CI_OPTION_LETTER = {"self-hosted": "a", "github-hosted": "b", "cloud": "c"}
# The owner's names (CIR10): Option 1 to 3 are the three config values. Option 4 (own runners first, a fallback
# after a wait) is the `ci.fallback` block; it is built in a later step, so it is not a config value yet.
CI_OPTION_NUMBER = {"self-hosted": 1, "github-hosted": 2, "cloud": 3}
CI_OPTION_TEXT = {
    "self-hosted": "own self-hosted runners on any machines you run",
    "github-hosted": "GitHub-hosted runners",
    "cloud": "Claude cloud sessions (no Actions, no webhooks)",
}
RUNNER_WAIT_EXAMPLE_MIN = 10


def option_name(option) -> str:
    """'Option 1 (self-hosted)' for a config value; '' for anything else."""
    n = CI_OPTION_NUMBER.get(option)
    return "Option %d (%s)" % (n, option) if n else ""


def runner_steps(os_name: str, labels=None, wait_min: int = RUNNER_WAIT_EXAMPLE_MIN) -> list:
    """The by-hand steps to add one self-hosted runner on another machine, for that machine's OS. A plugin cannot do
    them: each needs a person on that machine and a registration token from GitHub."""
    labels = [x for x in (labels or []) if isinstance(x, str) and x] or ["self-hosted", os_name]
    lab = ",".join(labels)
    if os_name == "windows":
        install = ["download the Windows x64 runner from the first step's page and unpack it, for example to C:\\actions-runner",
                   "in PowerShell there: .\\config.cmd --runasservice --url https://github.com/OWNER/REPO --token TOKEN --labels %s" % lab,
                   "if you did not ask for a service, start .\\run.cmd by hand while you need the runner"]
    elif os_name == "macos":
        install = ["download the macOS runner from that page and unpack it",
                   "./config.sh --url https://github.com/OWNER/REPO --token TOKEN --labels %s" % lab,
                   "./svc.sh install && ./svc.sh start"]
    else:
        install = ["download the Linux runner from that page and unpack it",
                   "./config.sh --url https://github.com/OWNER/REPO --token TOKEN --labels %s" % lab,
                   "sudo ./svc.sh install && sudo ./svc.sh start"]
    return (["open the repository's Settings > Actions > Runners > New self-hosted runner and pick %s (it shows the token)" % os_name]
            + install
            + ["add the machine to `runners` in .delivery/config.json (name, os, labels as above)",
               "run delivery_doctor.py: it checks the runner list again"])


def add_runner_advice(wait_min: int = RUNNER_WAIT_EXAMPLE_MIN) -> str:
    return ("a job that waits more than %d min for a runner means: add a runner with the same label on another machine"
            % wait_min)
DEFAULT_SHARD_TABLE = "scripts/delivery/ci-shards.json"
DEFAULT_RESULTS_PREFIX = "ci-result"


def ci_options(cfg) -> dict:
    """ci.options as {os: option} for the OS names that hold a valid option. There is no default: an OS that is
    not chosen is simply absent."""
    o = _section(_section(cfg, "ci"), "options")
    return {k: v for k, v in o.items() if k in CI_OS and v in CI_OPTIONS}


def ci_cloud(cfg) -> dict:
    c = _section(_section(cfg, "ci"), "cloud")
    return {"repo": c.get("repo") if isinstance(c.get("repo"), str) else "",
            "status_token_env": c.get("status_token_env") if isinstance(c.get("status_token_env"), str) else "",
            "branches": [x for x in c.get("branches", []) if isinstance(x, str)] if isinstance(c.get("branches"), list) else [],
            "results_prefix": c.get("results_prefix") if isinstance(c.get("results_prefix"), str) and c.get("results_prefix")
            else DEFAULT_RESULTS_PREFIX,
            "shard_timeout_min": c.get("shard_timeout_min") if isinstance(c.get("shard_timeout_min"), (int, float))
            and not isinstance(c.get("shard_timeout_min"), bool) and c.get("shard_timeout_min") >= 1 else 60}


def shard_table_path(root, cfg) -> str:
    v = _section(cfg, "ci").get("shard_table")
    rel = v if isinstance(v, str) and v.strip() else DEFAULT_SHARD_TABLE
    return os.path.join(root, *rel.split("/"))


def load_shards(root, cfg):
    """(shards, error). A shard is {id, os, commands, context}; context falls back to the id. error is None for a
    good table, a message for a missing or bad one (shards is [] then)."""
    path = shard_table_path(root, cfg)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], "no shard table at %s" % os.path.relpath(path, root).replace(os.sep, "/")
    except (OSError, ValueError) as exc:
        return [], "shard table is not readable JSON (%s)" % exc
    raw = data.get("shards") if isinstance(data, dict) else None
    if not isinstance(raw, list) or not raw:
        return [], "shard table has no shards"
    out, seen = [], set()
    for i, sh in enumerate(raw):
        if not isinstance(sh, dict) or not isinstance(sh.get("id"), str) or not sh["id"].strip():
            return [], "shard %d has no id" % i
        if sh["id"] in seen:
            return [], "shard id %r is used twice" % sh["id"]
        seen.add(sh["id"])
        osn = sh.get("os")
        if osn not in CI_OS:
            return [], "shard %r: os must be one of %s" % (sh["id"], ", ".join(CI_OS))
        cmds = sh.get("commands")
        if not isinstance(cmds, list) or not cmds or not all(isinstance(c, str) and c.strip() for c in cmds):
            return [], "shard %r: commands must be a non-empty list of strings" % sh["id"]
        ctx = sh.get("context") if isinstance(sh.get("context"), str) and sh.get("context").strip() else sh["id"]
        out.append({"id": sh["id"], "os": osn, "commands": cmds, "context": ctx})
    return out, None


def cloud_contexts(root, cfg) -> list:
    """The status contexts the watcher needs for option c: the context of every shard whose OS is cloud."""
    opts = ci_options(cfg)
    shards, _ = load_shards(root, cfg)
    seen, out = set(), []
    for sh in shards:
        if opts.get(sh["os"]) == "cloud" and sh["context"] not in seen:
            seen.add(sh["context"])
            out.append(sh["context"])
    return out


def load_tz(name):
    """The zone `name` as a tzinfo; raises ValueError with the cause and the fix when it cannot be loaded."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001 - ZoneInfoNotFoundError, ValueError, ImportError
        if name in ("UTC", "Etc/UTC"):       # UTC needs no database
            from datetime import timezone
            return timezone.utc
        raise ValueError("time zone %r cannot be loaded (%s: %s). Install tzdata (`pip install tzdata`; on Windows "
                         "it is not bundled) or fix the `tz` key; without it times would silently be UTC."
                         % (name, type(exc).__name__, exc)) from exc


# --- the validator ---------------------------------------------------------------------------------

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "number": (int, float), "integer": int}


def _is(value, typ):
    if typ in ("number", "integer") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[typ])


def _check(value, schema, path, errors, warnings):
    typ = schema.get("type")
    if "oneOf" in schema:
        trials = []
        for sub in schema["oneOf"]:
            e, w = [], []
            _check(value, sub, path, e, w)
            trials.append((e, w))
        ok = [t for t in trials if not t[0]]
        if len(ok) != 1:
            errors.append("%s: does not match exactly one allowed form (%s)" % (path, "; ".join(
                x for e, _ in trials for x in e[:1])))
        else:
            warnings.extend(ok[0][1])
        return
    if typ and not _is(value, typ):
        errors.append("%s: expected %s, got %s" % (path, typ, type(value).__name__))
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: %r is not one of %s" % (path, value, schema["enum"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema and value < schema["minimum"]:
        errors.append("%s: %r is below the minimum %s" % (path, value, schema["minimum"]))
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append("%s: %r does not match %s" % (path, value, schema["pattern"]))
        if schema.get("format") == "regex":
            try:
                re.compile(value)
            except re.error as exc:
                errors.append("%s: not a valid regular expression (%s)" % (path, exc))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append("%s: needs at least %d item(s)" % (path, schema["minItems"]))
        if "items" in schema:
            for i, item in enumerate(value):
                _check(item, schema["items"], "%s[%d]" % (path, i), errors, warnings)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errors.append("%s: missing required key %r" % (path, req))
        extra = schema.get("additionalProperties")
        for k, v in value.items():
            if k in props:
                _check(v, props[k], "%s.%s" % (path, k) if path else k, errors, warnings)
            elif isinstance(extra, dict):
                _check(v, extra, "%s.%s" % (path, k) if path else k, errors, warnings)
            elif not k.startswith("_") and props:
                warnings.append("%s: unknown key (ignored)" % (("%s.%s" % (path, k)) if path else k))


def load_schema(path=SCHEMA_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_config(cfg, schema=None):
    """(errors, warnings) for a parsed config."""
    errors, warnings = [], []
    if not isinstance(cfg, dict):
        return ["config: expected an object"], []
    _check(cfg, schema or load_schema(), "", errors, warnings)
    if isinstance(cfg.get("tz"), str) and cfg["tz"]:
        try:
            load_tz(cfg["tz"])
        except ValueError as exc:
            errors.append("tz: %s" % exc)
    for sect in ("watcher",):
        w = _section(cfg, sect)
        if any(isinstance(w.get(k), str) and "--auto" in w[k] for k in ("merge_method", "merge_flag")):
            errors.append("watcher: --auto is never used (D5); merges are `gh pr merge --merge`")
    return errors, warnings


def config_file(root=None, config=None):
    return config or os.path.join(root or ".", ".delivery", "config.json")


def validate_file(path):
    """(errors, warnings, status): status 'ok', 'missing' or 'unreadable'."""
    if not os.path.isfile(path):
        return [], [], "missing"
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as exc:
        return ["%s: not readable JSON (%s)" % (path, exc)], [], "unreadable"
    e, w = validate_config(cfg)
    return e, w, "ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_config.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="action", required=True)
    v = sub.add_parser("validate", help="validate .delivery/config.json against the schema")
    v.add_argument("--root", default=".", help="repository root (holds .delivery/)")
    v.add_argument("--config", help="config file instead of <root>/.delivery/config.json")
    v.add_argument("--json", action="store_true", help="machine-readable result")
    v.add_argument("--strict", action="store_true", help="warnings (unknown keys) fail too")
    args = ap.parse_args(argv)
    path = config_file(args.root, args.config)
    errors, warnings, status = validate_file(path)
    if args.json:
        print(json.dumps({"file": path, "status": status, "errors": errors, "warnings": warnings}))
    else:
        if status == "missing":
            print("%s: no config file; defaults apply" % path)
        for e in errors:
            print("error: " + e)
        for w in warnings:
            print("warning: " + w)
        if not errors and status == "ok":
            print("%s: valid (%d warning(s))" % (path, len(warnings)))
    if status == "unreadable":
        return 2
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
