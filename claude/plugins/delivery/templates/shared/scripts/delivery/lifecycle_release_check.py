#!/usr/bin/env python3
"""DS235d: release check for the lifecycle lanes (DELIVERYSPEC LC-32, and the lane results of LC-8 to LC-21).

  lifecycle_release_check.py check --lifecycle lifecycle.json --results DIR [--release] [--artifacts DIR] [--config .delivery/config.json]
                                   [--table scripts/delivery/ci-shards.json] [--default main] [--root .]
                                   [--base REF | --changed-file FILE]
  lifecycle_release_check.py write-result --lane L --arch A --package P --steps steps.txt --out result.json

`check` reads the targets from lifecycle.json. On a release pull request (--release) it fails unless every
target the pull request affects has a passing lane result (DL-125: with --base REF or --changed-file, the map is
affected_targets.py; with neither, every target is affected) and every other target has a passing result that is a
pass record of the default branch. A target that is not listed is not required. With --artifacts it also checks
the artifact names `<Product>-<version>-<os>-<arch>.<ext>` and, from the config, that public packages and private
user data live in separate stores (LC-32). Exit 0 pass, 1 fail, 2 bad input.

A lane result may come from a pass record (DL-118: `pass_records.py to-result` writes `status: pass`,
`source: "record"`, `shard`, `key`, `record_branch`). It counts only when `record_branch` is the default branch and
its `key` equals the inputs key computed now for its shard from the table (`--table`, `--root`). A record of
another branch, another key, a shard with no key, or an unreadable table is refused, and the lane must run.
A lane with no `inputs` list has no key and always runs.
"""
import argparse
import json
import re
import sys
from pathlib import Path

EXT = {"msi": "msi", "deb": "deb", "rpm": "rpm", "pkg": "pkg", "tar": "tar.gz", "zip": "zip"}
OS_WORD = {"windows": "win", "linux": "linux", "macos": "macos"}
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


def record_problem(r, key_of, default):
    """Why a result written from a pass record is refused, or None."""
    if r.get("record_branch") != default:
        return "record is from branch %r, not %s" % (r.get("record_branch"), default)
    want = key_of(r) if key_of else None
    if not want:
        return "this pull request has no inputs key for the lane"
    if r.get("key") != want:
        return "record key differs from this pull request's key"
    return None


def check_lanes(targets, results, key_of=None, default="main", unaffected=()):
    """A list of problems; empty when every target has a passing lane result.
    key_of(result) is the inputs key now for a record result's shard (DL-118).
    unaffected is the set of target keys the change does not touch (DL-125): they need a pass record of the
    default branch; a live pass is accepted too."""
    problems = []
    for t in targets:
        key = target_key(t)
        name = "%s %s %s" % key
        r = results.get(key)
        if r is None and key in unaffected:
            problems.append("%s: not affected, but no pass record of %s and no lane result" % (name, default))
        elif r is None:
            problems.append("%s: no lane result" % name)
        elif r.get("status") != "pass":
            failed = ", ".join(r.get("failed") or []) or "lane not green"
            problems.append("%s: lane failed (%s)" % (name, failed))
        elif r.get("source") == "record":
            why = record_problem(r, key_of, default)
            if why:
                problems.append("%s: pass record refused (%s)" % (name, why))
    return problems


def make_key_of(root, table_path):
    """A function: result -> the inputs key of its shard now, or None (no shard, no table, no key)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pass_records as P
        table = P.load_table(str(root), table_path)
    except (ImportError, OSError, ValueError):
        return lambda r: None

    def key_of(r):
        shard = r.get("shard")
        return P.inputs_key(str(root), table, shard)[0] if shard else None
    return key_of


def unaffected_keys(lifecycle, targets, base, changed_file):
    """Target keys the change does not affect (DL-125); empty without --base or --changed-file or on any error."""
    if not base and not changed_file:
        return set()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import affected_targets as A
        import area_select as AS
        changed = []
        if changed_file:
            changed += [x for x in Path(changed_file).read_text(encoding="utf-8").splitlines() if x.strip()]
        if base:
            changed += AS.changed_from_git(base)
        lc = load_json(lifecycle)
        res = A.decide(changed, lc)
    except (ImportError, OSError, ValueError):
        return set()
    names = set(res["targets"])
    return {target_key(t) for t in targets if A.name_of(t) not in names}


def os_word(target):
    return OS_WORD[target["os"]]


def artifact_re(product, os_name, arch, package):
    """os_name is the word in the file name: win, linux or macos."""
    return re.compile(r"^%s-\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?-%s-%s\.%s$"
                      % (re.escape(product), re.escape(os_name), re.escape(arch), re.escape(EXT[package])))


def check_names(product, targets, names):
    """Every target has an artifact named <Product>-<version>-<os>-<arch>.<ext>; no artifact has another shape."""
    problems = []
    if not re.fullmatch(r"[A-Za-z0-9]+", product or ""):
        problems.append("product %r must be one word of letters and digits" % product)
    for t in targets:
        rx = artifact_re(product, os_word(t), t["arch"], t["package"])
        if not any(rx.match(n) for n in names):
            problems.append("no artifact named %s-<version>-%s-%s.%s" % (product, os_word(t), t["arch"], EXT[t["package"]]))
    exts = tuple("." + e for e in EXT.values())
    for n in names:
        if n.endswith(exts) and not any(artifact_re(product, os_word(t), t["arch"], t["package"]).match(n) for t in targets):
            problems.append("artifact %s does not match <Product>-<version>-<os>-<arch>.<ext>" % n)
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
        off = unaffected_keys(a.lifecycle, targets, a.base, a.changed_file)
        if off:
            print("not affected, proven by a pass record of %s: %s" % (a.default, ", ".join("%s %s %s" % k for k in sorted(off, key=str))))
        problems += check_lanes(targets, load_results(a.results) if a.results else {},
                                make_key_of(a.root, a.table), a.default, off)
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
    c.add_argument("--table", default="scripts/delivery/ci-shards.json")
    c.add_argument("--default", default="main")
    c.add_argument("--root", default=".")
    c.add_argument("--base", help="DL-125: the base ref; targets the diff does not affect need a pass record of main")
    c.add_argument("--changed-file", help="DL-125: a file listing the changed paths")
    w = sub.add_parser("write-result")
    for k in ("lane", "arch", "package", "steps", "out"):
        w.add_argument("--" + k, required=True)
    a = ap.parse_args(argv)
    return cmd_check(a) if a.cmd == "check" else cmd_write(a)


if __name__ == "__main__":
    sys.exit(main())
