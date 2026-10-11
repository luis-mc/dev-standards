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


def main(argv: list[str] | None = None) -> int:
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
