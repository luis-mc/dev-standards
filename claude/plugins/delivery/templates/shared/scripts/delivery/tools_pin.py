#!/usr/bin/env python3
"""Pin a scanner's release checksums into tools.json (maintainer use).

    tools_pin.py gitleaks 8.30.1

Downloads the release's checksums file once, takes the SHA-256 of the five
archives agent_setup.sh and ci.yml install (linux_x64, linux_arm64, darwin_x64,
darwin_arm64, windows_x64) and rewrites tools.json:

    {"gitleaks": {"version": "8.30.1", "sha256": {"linux_x64": "...", ...}}}

After that, agent_setup.sh and CI verify the downloaded archive against these
values and never fetch the checksums file again. Review the diff, and check one
archive yourself (`sha256sum` of the download) before committing.

More pins (DS199), same file, other tools left as they are:

    tools_pin.py rustup-init 1.29.3
    tools_pin.py crate cargo-deny 0.20.2 [--index-file FILE]
    tools_pin.py entry llvm 20.1.8 --platform linux_x64 --kind archive \
        --url URL --sha256 HEX [--bin-dir DIR] [--bin NAME]

`rustup-init` reads the .sha256 file beside each rustup-init download.
`crate` reads the cksum of that version from the crates.io sparse index (or
FILE, one JSON line per version) and pins the static.crates.io .crate for all
five platforms. `entry` records one platform of any archive or file tool; use
it for LLVM and Zig after you hash the download yourself. Entries merge into
tools.json; they never replace other platforms or other tools. See ci_tool.py
for the entry fields.

Options:
  --checksums FILE    read this checksums file instead of downloading it
  --base-url URL      release download base URL (default: the GitHub release)
  --tools-json FILE   file to rewrite (default: tools.json next to this script)

Exit: 0 written, 1 a platform is missing from the checksums, 2 usage or download
error. Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PLATFORMS = {
    "linux_x64": "linux_x64.tar.gz",
    "linux_arm64": "linux_arm64.tar.gz",
    "darwin_x64": "darwin_x64.tar.gz",
    "darwin_arm64": "darwin_arm64.tar.gz",
    "windows_x64": "windows_x64.zip",
}
DEFAULT_BASE = "https://github.com/gitleaks/gitleaks/releases/download/v{version}"


def parse_checksums(text: str) -> dict[str, str]:
    """`<sha256>  <file>` lines (a leading `*` on the file name is allowed)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            out[parts[1].lstrip("*")] = parts[0].lower()
    return out


RUSTUP_TARGETS = {
    "linux_x64": ("x86_64-unknown-linux-gnu", "rustup-init"),
    "linux_arm64": ("aarch64-unknown-linux-gnu", "rustup-init"),
    "darwin_x64": ("x86_64-apple-darwin", "rustup-init"),
    "darwin_arm64": ("aarch64-apple-darwin", "rustup-init"),
    "windows_x64": ("x86_64-pc-windows-msvc", "rustup-init.exe"),
}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode("utf-8")


def _merge(data: dict, name: str, version: str, entries: dict, kind: str | None = None) -> None:
    old = data.get(name)
    if not isinstance(old, dict) or old.get("version") != version:
        old = {"version": version, "platforms": {}}
    old.setdefault("platforms", {}).update(entries)
    data[name] = old


def main_more(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tools_pin.py")
    ap.add_argument("cmd", choices=["rustup-init", "crate", "entry"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--tools-json", metavar="FILE",
                    default=str(Path(__file__).resolve().parent / "tools.json"))
    ap.add_argument("--index-file", metavar="FILE")
    ap.add_argument("--platform", choices=list(PLATFORMS))
    ap.add_argument("--kind", choices=["file", "archive", "crate"], default="archive")
    ap.add_argument("--url")
    ap.add_argument("--sha256")
    ap.add_argument("--bin-dir")
    ap.add_argument("--bin")
    a = ap.parse_args(argv)
    path = Path(a.tools_json)
    try:
        data = _load(path)
    except ValueError as exc:
        print(f"tools_pin: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    try:
        if a.cmd == "rustup-init":
            if len(a.args) != 1:
                ap.error("rustup-init takes a version")
            version = a.args[0]
            entries = {}
            for plat, (target, exe) in RUSTUP_TARGETS.items():
                url = f"https://static.rust-lang.org/rustup/archive/{version}/{target}/{exe}"
                got = _get(url + ".sha256").split()
                if not got or not re.fullmatch(r"[0-9a-fA-F]{64}", got[0]):
                    print(f"tools_pin: no SHA-256 at {url}.sha256", file=sys.stderr)
                    return 1
                entries[plat] = {"kind": "file", "url": url, "sha256": got[0].lower(),
                                 "file": f"rustup-init-{target}" + (".exe" if exe.endswith(".exe") else ""),
                                 "bin": "rustup-init"}
            _merge(data, "rustup-init", version, entries)
            name = "rustup-init"
        elif a.cmd == "crate":
            if len(a.args) != 2:
                ap.error("crate takes a name and a version")
            name, version = a.args
            if a.index_file:
                text = Path(a.index_file).read_text(encoding="utf-8")
            else:
                n = name.lower()
                shard = {1: "1", 2: "2"}.get(len(n)) or (f"3/{n[0]}" if len(n) == 3 else f"{n[:2]}/{n[2:4]}")
                text = _get(f"https://index.crates.io/{shard}/{n}")
            cksum = None
            for line in text.splitlines():
                row = json.loads(line)
                if row.get("name") == name and row.get("vers") == version:
                    cksum = row.get("cksum")
            if not cksum or not re.fullmatch(r"[0-9a-f]{64}", cksum):
                print(f"tools_pin: {name} {version} is not in the crates index", file=sys.stderr)
                return 1
            url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
            entry = {"kind": "crate", "url": url, "sha256": cksum, "bin": name}
            _merge(data, name, version, {p: dict(entry) for p in PLATFORMS})
        else:
            if len(a.args) != 2 or not (a.platform and a.url and a.sha256):
                ap.error("entry takes a name and a version, with --platform, --url and --sha256")
            name, version = a.args
            if not re.fullmatch(r"[0-9a-fA-F]{64}", a.sha256):
                print("tools_pin: --sha256 is not 64 hex digits", file=sys.stderr)
                return 2
            entry = {"kind": a.kind, "url": a.url, "sha256": a.sha256.lower()}
            if a.bin_dir:
                entry["bin_dir"] = a.bin_dir
            if a.bin:
                entry["bin"] = a.bin
            _merge(data, name, version, {a.platform: entry})
    except (OSError, ValueError) as exc:
        print(f"tools_pin: {exc}", file=sys.stderr)
        return 2
    _save(path, data)
    print(f"tools_pin: {name} pinned in {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("rustup-init", "crate", "entry"):
        return main_more(argv)
    ap = argparse.ArgumentParser(description="Pin a scanner's SHA-256 values into tools.json.")
    ap.add_argument("tool", choices=["gitleaks"])
    ap.add_argument("version", help="exact x.y.z release")
    ap.add_argument("--checksums", metavar="FILE")
    ap.add_argument("--base-url", metavar="URL")
    ap.add_argument("--tools-json", metavar="FILE",
                    default=str(Path(__file__).resolve().parent / "tools.json"))
    args = ap.parse_args(argv)

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        print(f"tools_pin: {args.version!r} is not an exact x.y.z version", file=sys.stderr)
        return 2
    name = f"gitleaks_{args.version}_checksums.txt"
    if args.checksums:
        try:
            text = Path(args.checksums).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"tools_pin: cannot read {args.checksums}: {exc}", file=sys.stderr)
            return 2
    else:
        base = (args.base_url or DEFAULT_BASE.format(version=args.version)).rstrip("/")
        try:
            with urllib.request.urlopen(f"{base}/{name}", timeout=60) as resp:
                text = resp.read().decode("utf-8")
        except (OSError, ValueError) as exc:  # URLError is an OSError
            print(f"tools_pin: cannot download {base}/{name}: {exc}", file=sys.stderr)
            return 2

    sums = parse_checksums(text)
    pins: dict[str, str] = {}
    missing = []
    for key, suffix in PLATFORMS.items():
        asset = f"gitleaks_{args.version}_{suffix}"
        if asset in sums:
            pins[key] = sums[asset]
        else:
            missing.append(asset)
    if missing:
        print("tools_pin: not in the checksums file: " + ", ".join(missing), file=sys.stderr)
        return 1

    path = Path(args.tools_json)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"tools_pin: {path} is not valid JSON: {exc}", file=sys.stderr)
            return 2
    data["gitleaks"] = {"version": args.version, "sha256": pins}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"tools_pin: gitleaks {args.version} pinned for {len(pins)} platforms in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
