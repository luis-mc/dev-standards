#!/usr/bin/env python3
"""DS235d: release check for the lifecycle lanes (DELIVERYSPEC LC-32, and the lane results of LC-8 to LC-21).

  lifecycle_release_check.py check --lifecycle lifecycle.json --results DIR [--release] [--artifacts DIR] [--config .delivery/config.json]
  lifecycle_release_check.py write-result --lane L --arch A --package P --steps steps.txt --out result.json

`check` reads the targets from lifecycle.json. On a release pull request (--release) it fails unless every
target has a passing lane result. A target that is not listed is not required. With --artifacts it also checks
the artifact names `<Product>-<version>-<arch>.<ext>` and, from the config, that public packages and private
user data live in separate stores (LC-32). Exit 0 pass, 1 fail, 2 bad input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

EXT = {"msi": "msi", "deb": "deb", "rpm": "rpm", "pkg": "pkg", "tar": "tar.gz"}
LINE = re.compile(r"^(LC-\d+)\s+(PASS|FAIL)\b", re.M)


def lane_of(target):
    """The lane a target runs in: its distro on Linux, else its OS."""
    return target.get("distro") or target["os"]


def target_key(target):
    return (lane_of(target), target.get("arch"), target.get("package"))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_results(folder):
    out = {}
    for f in sorted(Path(folder).rglob("*.json")):
        try:
            r = load_json(f)
        except (OSError, ValueError):
            continue
        if isinstance(r, dict) and r.get("lane"):
            out[(r["lane"], r.get("arch"), r.get("package"))] = r
    return out


def check_lanes(targets, results):
    """A list of problems; empty when every target has a passing lane result."""
    problems = []
    for t in targets:
        key = target_key(t)
        name = "%s %s %s" % key
        r = results.get(key)
        if r is None:
            problems.append("%s: no lane result" % name)
        elif r.get("status") != "pass":
            failed = ", ".join(r.get("failed") or []) or "lane not green"
            problems.append("%s: lane failed (%s)" % (name, failed))
    return problems


def artifact_re(product, arch, package):
    return re.compile(r"^%s-\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?-%s\.%s$"
                      % (re.escape(product), re.escape(arch), re.escape(EXT[package])))


def check_names(product, targets, names):
    """Every target has an artifact named <Product>-<version>-<arch>.<ext>; no artifact has another shape."""
    problems = []
    for t in targets:
        rx = artifact_re(product, t["arch"], t["package"])
        if not any(rx.match(n) for n in names):
            problems.append("no artifact named %s-<version>-%s.%s" % (product, t["arch"], EXT[t["package"]]))
    exts = tuple("." + e for e in EXT.values())
    for n in names:
        if n.endswith(exts) and not any(artifact_re(product, t["arch"], t["package"]).match(n) for t in targets):
            problems.append("artifact %s does not match <Product>-<version>-<arch>.<ext>" % n)
    return problems


def check_stores(config):
    """Public packages and private user data live in separate stores (LC-32)."""
    stores = ((config.get("lifecycle") or {}).get("stores")) or {}
    pub, priv = stores.get("public_packages"), stores.get("private_data")
    if not pub or not priv:
        return ["config lifecycle.stores needs public_packages and private_data"]
    if pub == priv:
        return ["public packages and private user data share one store (%s)" % pub]
    return []


def cmd_check(a):
    try:
        lc = load_json(a.lifecycle)
        targets = lc.get("targets") or []
    except (OSError, ValueError) as e:
        print("cannot read %s: %s" % (a.lifecycle, e), file=sys.stderr)
        return 2
    problems = []
    if a.release:
        problems += check_lanes(targets, load_results(a.results) if a.results else {})
    else:
        print("not a release pull request: lane results are not required")
    if a.artifacts:
        names = [p.name for p in Path(a.artifacts).iterdir() if p.is_file()]
        problems += check_names(lc.get("product", ""), targets, names)
        try:
            cfg = load_json(a.config)
        except (OSError, ValueError):
            cfg = {}
        problems += check_stores(cfg)
    for p in problems:
        print("FAIL " + p)
    if not problems:
        print("OK lifecycle release check (%d target%s)" % (len(targets), "" if len(targets) == 1 else "s"))
    return 1 if problems else 0


def cmd_write(a):
    text = Path(a.steps).read_text(encoding="utf-8", errors="replace") if Path(a.steps).exists() else ""
    marks = LINE.findall(text)
    failed = sorted({i for i, s in marks if s == "FAIL"})
    status = "pass" if marks and not failed else "fail"
    Path(a.out).write_text(json.dumps({"lane": a.lane, "arch": a.arch, "package": a.package,
                                       "status": status, "failed": failed, "checks": len(marks)}, indent=2) + "\n")
    print("%s %s %s %s" % (a.lane, a.arch, a.package, status))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--lifecycle", required=True)
    c.add_argument("--results")
    c.add_argument("--release", action="store_true")
    c.add_argument("--artifacts")
    c.add_argument("--config", default=".delivery/config.json")
    w = sub.add_parser("write-result")
    for k in ("lane", "arch", "package", "steps", "out"):
        w.add_argument("--" + k, required=True)
    a = ap.parse_args(argv)
    return cmd_check(a) if a.cmd == "check" else cmd_write(a)


if __name__ == "__main__":
    sys.exit(main())
