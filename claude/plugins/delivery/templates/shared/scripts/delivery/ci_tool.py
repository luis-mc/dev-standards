#!/usr/bin/env python3
"""Fetch a pinned CI tool into a cache that survives the job (DL115).

    ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>
    ci_tool.py gitleaks [--platform linux_x64|linux_arm64|darwin_x64|darwin_arm64|windows_x64]

`fetch` prints the absolute path of the verified file on stdout, and nothing
else. `gitleaks` reads tools.json next to this script, fetches that platform's
archive the same way, extracts the gitleaks binary into the cache folder once,
and prints the binary's path. The default platform is the current one.

Rules:
  - Cache folder: env CI_TOOLS_DIR if set, else C:/ci-tools on Windows and
    ~/.cache/ci-tools elsewhere. Layout: <dir>/<tool>/<version>/<file>. It is
    never $RUNNER_TEMP or the workspace, which are wiped every job. If
    CI_TOOLS_DIR cannot be written, one warning goes to stderr and the default
    folder is used.
  - A cached file is used only when its SHA-256 equals the pin. A file that
    does not match is deleted and fetched again.
  - Fetch: 5 attempts, a wait of 10 s then longer between them (env
    CI_TOOL_RETRY_DELAY sets the base wait in seconds), 20 s connect timeout,
    retry on any error including 5xx. The download goes to <file>.partial
    (unique per process), is verified, then renamed with os.replace, so a job
    racing on the same runner never sees a half file. HTTPS_PROXY is honoured
    as urllib does.
  - The `.partial` file never remains, also after an error.

Exit: 0 the path was printed, 1 a download, checksum or extract failure (one
line on stderr: URL, attempt count, last error), 2 usage error.
Python 3.10+, standard library only, Windows and Linux.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ATTEMPTS = 5
CONNECT_TIMEOUT = 20
DEFAULT_DELAY = 10.0
GITLEAKS_URL = "https://github.com/gitleaks/gitleaks/releases/download/v{version}/gitleaks_{version}_{platform}.{ext}"
PLATFORMS = ("linux_x64", "linux_arm64", "darwin_x64", "darwin_arm64", "windows_x64")


class ToolError(Exception):
    pass


def cache_dir() -> Path:
    env = os.environ.get("CI_TOOLS_DIR")
    default = Path("C:/ci-tools") if os.name == "nt" else Path.home() / ".cache" / "ci-tools"
    if env:
        try:
            Path(env).mkdir(parents=True, exist_ok=True)
            if os.access(env, os.W_OK):
                return Path(env).resolve()
        except OSError:
            pass
        print(f"ci_tool: CI_TOOLS_DIR {env} is not writable; using {default}", file=sys.stderr)
    return default


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _delay(attempt: int) -> float:
    try:
        base = float(os.environ.get("CI_TOOL_RETRY_DELAY", DEFAULT_DELAY))
    except ValueError:
        base = DEFAULT_DELAY
    return base * attempt  # 10 s, 20 s, 30 s, 40 s


def _download(url: str, partial: Path) -> None:
    with urllib.request.urlopen(url, timeout=CONNECT_TIMEOUT) as resp, open(partial, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)


def fetch(url: str, sha256: str, name: str) -> Path:
    sha256 = sha256.lower()
    parts = [p for p in name.replace("\\", "/").split("/") if p]
    if len(parts) != 3 or ".." in parts or "." in parts:
        raise ValueError("--name must be <tool>/<version>/<file>")
    target = cache_dir().joinpath(*parts)
    if target.is_file():
        if sha256_of(target) == sha256:
            return target.resolve()
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f"{target.name}.{os.getpid()}.partial")
    last = "no attempt"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            _download(url, partial)
            got = sha256_of(partial)
            if got != sha256:
                raise ToolError(f"checksum mismatch: expected {sha256}, got {got}")
            os.replace(partial, target)
            return target.resolve()
        except Exception as exc:  # any error is retried, 5xx included
            last = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                partial.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if attempt < ATTEMPTS:
            time.sleep(_delay(attempt))
    raise ToolError(f"cannot fetch {url} after {ATTEMPTS} attempts: {last}")


def current_platform() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    system = {"linux": "linux", "darwin": "darwin", "win32": "windows"}.get(sys.platform, "linux")
    return f"{system}_{arch}"


def gitleaks(plat: str) -> Path:
    pin_file = Path(__file__).resolve().parent / "tools.json"
    try:
        g = json.loads(pin_file.read_text(encoding="utf-8"))["gitleaks"]
        version, sha = g["version"], g["sha256"][plat]
    except (OSError, ValueError, KeyError, TypeError):
        raise ToolError(
            f"{pin_file} has no pinned SHA-256 for gitleaks on {plat}. "
            "Run: python3 scripts/delivery/tools_pin.py gitleaks <version>"
        )
    ext = "zip" if plat.startswith("windows") else "tar.gz"
    archive_name = f"gitleaks_{version}_{plat}.{ext}"
    url = GITLEAKS_URL.format(version=version, platform=plat, ext=ext)
    archive = fetch(url, sha, f"gitleaks/{version}/{archive_name}")
    exe = "gitleaks.exe" if plat.startswith("windows") else "gitleaks"
    binary = archive.parent / f"{plat}-{exe}"
    if binary.is_file():
        return binary
    tmp = binary.with_name(f"{binary.name}.{os.getpid()}.partial")
    try:
        if ext == "zip":
            with zipfile.ZipFile(archive) as z, z.open(exe) as src, open(tmp, "wb") as out:
                out.write(src.read())
        else:
            with tarfile.open(archive) as t:
                member = t.extractfile("gitleaks")
                if member is None:
                    raise ToolError(f"{archive} has no gitleaks binary")
                tmp.write_bytes(member.read())
        os.chmod(tmp, 0o755)
        os.replace(tmp, binary)
    except (OSError, KeyError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ToolError(f"cannot extract gitleaks from {archive}: {exc}")
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return binary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ci_tool.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("url")
    f.add_argument("--sha256", required=True)
    f.add_argument("--name", required=True)
    g = sub.add_parser("gitleaks")
    g.add_argument("--platform", choices=PLATFORMS, default=None)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        if args.cmd == "fetch":
            path = fetch(args.url, args.sha256, args.name)
        else:
            path = gitleaks(args.platform or current_platform())
    except ValueError as exc:
        print(f"ci_tool: {exc}", file=sys.stderr)
        return 2
    except ToolError as exc:
        print(f"ci_tool: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
