#!/usr/bin/env python3
"""DL295: decide how much of the Rust workspace a pull request must build and test.

  rust_scope.py --event E --head-ref R [--diff-base REF] [--config FILE] [--github-output]

Writes run=, full=, crates=, why= (to $GITHUB_OUTPUT with --github-output, else to stdout).

  run=false   a pull request whose diff touches no Rust path
  full=true   not a pull request, a release pull request, an unreadable diff, a workspace-wide
              input (lockfile, toolchain, .cargo, ...), a new crate folder, or no crate placed
  crates=     else: the touched member crates plus every member that depends on them (space separated)

Standard library only. Over-including a crate is fine; missing one is not.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE_WIDE = (
    "Cargo.toml", "Cargo.lock", "rust-toolchain", "rustfmt.toml", "deny.toml", ".cargo/", "vendor/",
    "scripts/delivery/rust_ci.py", "scripts/delivery/rust_scope.py", "scripts/delivery/tools.json",
    ".github/workflows/ci.yml",
)
DEFAULT_RELEASE_RE = r"^release/.+"
DEP_SECTION = re.compile(r"^\[(?:[^\]]*\.)?(?:dependencies|dev-dependencies|build-dependencies)(?:\.([^\]]+))?\]\s*$")


def _toml_strings(text: str) -> list[str]:
    return re.findall(r'"([^"]*)"', text)


def workspace_members(root: Path) -> list[str]:
    """Member folders (posix, relative to root) from the root Cargo.toml [workspace] members."""
    try:
        text = (root / "Cargo.toml").read_text(encoding="utf-8")
    except OSError:
        return []
    m = re.search(r"^\[workspace\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not m:
        return []
    arr = re.search(r"^\s*members\s*=\s*\[(.*?)\]", m.group(1), re.M | re.S)
    if not arr:
        return []
    out: list[str] = []
    for pat in _toml_strings(re.sub(r"#.*", "", arr.group(1))):
        for hit in sorted(glob.glob(str(root / pat))):
            p = Path(hit)
            if p.is_dir():
                rel = p.relative_to(root).as_posix()
                if rel not in out:
                    out.append(rel)
    return out


def read_manifest(root: Path, folder: str) -> tuple[str | None, set[str], set[str]]:
    """(package name, dependency keys, dependency path folders) of one member."""
    try:
        text = (root / folder / "Cargo.toml").read_text(encoding="utf-8")
    except OSError:
        return None, set(), set()
    name = None
    keys: set[str] = set()
    paths: set[str] = set()
    section = ""
    for raw in text.splitlines():
        line = re.sub(r"\s#.*$", "", raw).strip()
        if line.startswith("["):
            section = line
            dm = DEP_SECTION.match(line)
            if dm and dm.group(1):
                keys.add(dm.group(1).strip().strip('"'))
            continue
        if section == "[package]":
            nm = re.match(r'^name\s*=\s*"([^"]+)"', line)
            if nm and name is None:
                name = nm.group(1)
            continue
        dm = DEP_SECTION.match(section)
        if not dm:
            continue
        if dm.group(1):  # [dependencies.foo]: the lines below describe foo
            pm = re.match(r'^path\s*=\s*"([^"]+)"', line)
            if pm:
                paths.add(os.path.normpath(os.path.join(folder, pm.group(1))).replace("\\", "/"))
            continue
        km = re.match(r'^([A-Za-z0-9_\-"]+)', line)
        if km and "=" in line:
            keys.add(km.group(1).strip('"'))
        for pm in re.finditer(r'path\s*=\s*"([^"]+)"', line):
            paths.add(os.path.normpath(os.path.join(folder, pm.group(1))).replace("\\", "/"))
    return name, keys, paths


def build_graph(root: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    """({folder: package name}, {folder: folders it depends on}) for the members."""
    members = workspace_members(root)
    names: dict[str, str] = {}
    raw: dict[str, tuple[set[str], set[str]]] = {}
    for f in members:
        name, keys, paths = read_manifest(root, f)
        if name:
            names[f] = name
            raw[f] = (keys, paths)
    by_name = {n: f for f, n in names.items()}
    deps: dict[str, set[str]] = {}
    for f, (keys, paths) in raw.items():
        d = {by_name[k] for k in keys if k in by_name}
        d |= {p for p in paths if p in names}
        d.discard(f)
        deps[f] = d
    return names, deps


def is_workspace_wide(path: str) -> bool:
    return any(path == w or (w.endswith(("/", "-")) and path.startswith(w)) for w in WORKSPACE_WIDE) \
        or path.startswith("rust-toolchain")


def under(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip("/") + "/")


def decide(root: Path, event: str, head_ref: str, changed: list[str] | None, release_re: str) -> dict:
    if event != "pull_request":
        return {"run": True, "full": True, "crates": "", "why": "not a pull request"}
    if re.search(release_re, head_ref or ""):
        return {"run": True, "full": True, "crates": "", "why": "release pull request"}
    if changed is None:
        return {"run": True, "full": True, "crates": "", "why": "diff unreadable"}
    names, deps = build_graph(root)
    members = workspace_members(root)
    touched: set[str] = set()
    rust_touched = False
    for p in changed:
        if is_workspace_wide(p):
            return {"run": True, "full": True, "crates": "", "why": "workspace-wide input: " + p}
        hit = [f for f in members if under(p, f)]
        if hit:
            rust_touched = True
            best = max(hit, key=len)
            if best in names:
                touched.add(best)
            else:
                return {"run": True, "full": True, "crates": "", "why": "member without manifest: " + best}
            continue
        # A crate folder that is not a member (new or renamed crate): scope cannot place it.
        if p.endswith(".rs") or p.rsplit("/", 1)[-1] == "Cargo.toml":
            return {"run": True, "full": True, "crates": "", "why": "unknown member folder: " + p}
    if not rust_touched:
        return {"run": False, "full": False, "crates": "", "why": "no Rust path changed"}
    if not touched:
        return {"run": True, "full": True, "crates": "", "why": "no crate placed"}
    out = set(touched)
    grew = True
    while grew:
        grew = False
        for f, d in deps.items():
            if f not in out and d & out:
                out.add(f)
                grew = True
    crates = sorted(names[f] for f in out)
    return {"run": True, "full": False, "crates": " ".join(crates), "why": "crates: " + " ".join(crates)}


def release_re_from(config: Path) -> str:
    import json
    try:
        cfg = json.loads(config.read_text(encoding="utf-8"))
        return (cfg.get("release_pr") or {}).get("head_re") or DEFAULT_RELEASE_RE
    except (OSError, ValueError, AttributeError):
        return DEFAULT_RELEASE_RE


def changed_files(root: Path, base: str) -> list[str] | None:
    try:
        res = subprocess.run(["git", "diff", "--name-only", base, "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return [ln.strip().replace("\\", "/") for ln in res.stdout.splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rust_scope.py", description=__doc__.split("\n")[0])
    ap.add_argument("--event", default="")
    ap.add_argument("--head-ref", default="")
    ap.add_argument("--diff-base", default="HEAD^1")
    ap.add_argument("--config", default="scripts/delivery/ci-scope.json")
    ap.add_argument("--github-output", action="store_true")
    args = ap.parse_args(argv)
    root = Path(os.environ.get("RUST_CI_ROOT") or os.getcwd())
    cfg = Path(args.config)
    rel = release_re_from(cfg if cfg.is_absolute() else root / cfg)
    changed = changed_files(root, args.diff_base) if args.event == "pull_request" else []
    res = decide(root, args.event, args.head_ref, changed, rel)
    lines = ["run=%s" % str(res["run"]).lower(), "full=%s" % str(res["full"]).lower(),
             "crates=%s" % res["crates"], "why=%s" % res["why"]]
    print("rust_scope: " + "; ".join(lines))
    target = os.environ.get("GITHUB_OUTPUT") if args.github_output else None
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    elif args.github_output:
        print("rust_scope: GITHUB_OUTPUT is not set", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
