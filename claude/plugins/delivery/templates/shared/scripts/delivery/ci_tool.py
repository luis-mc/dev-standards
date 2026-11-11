#!/usr/bin/env python3
"""Fetch a pinned CI tool into a cache that survives the job (DL115).

    ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>
    ci_tool.py gitleaks [--platform linux_x64|linux_arm64|darwin_x64|darwin_arm64|windows_x64]
    ci_tool.py tool <name> [--platform P] [--exe NAME] [--dir]

`fetch` prints the absolute path of the verified file on stdout, and nothing
else. `gitleaks` reads tools.json next to this script, fetches that platform's
archive the same way, extracts the gitleaks binary into the cache folder once,
and prints the binary's path. The default platform is the current one.

`tool` fetches any tool pinned in tools.json (DS199) and prints one path:
the tool's bin file, or with --exe NAME that file in the tool's bin folder, or
with --dir the bin folder. `gitleaks` is the same as `tool gitleaks` with the
gitleaks pin shape. A pin has "version" and "platforms": {<plat>: entry}.
Entry kinds:
  wheel    a PyPI .whl (a zip) that carries a binary (Zig). Like archive, but
           keeps the exec bit stored in the zip.
  file     one raw download (rustup-init). Cached, made executable.
  archive  a .tar.gz/.tar.xz/.zip (LLVM, Zig). Unpacked once into
           <tool>/<version>/unpacked-<plat>/. "bin_dir" is the folder with the
           executables, "bin" the default executable, both relative to it.
  crate    a crates.io source archive (cargo-deny, cargo-xwin). The .crate is
           verified, unpacked, and built once with `cargo install --locked
           --path <src> --root <tool>/<version>/root-<plat>`. Binaries land in
           root-<plat>/bin. Env CI_TOOL_CARGO names the cargo command.
Env CI_TOOLS_JSON names another pin file (tests).
Entry fields: "url", "sha256", optional "file" (cache name), "bin", "bin_dir".

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
  - Shared cache (DL194): when the cache root is world-writable (the pool's
    /ci-tools), each folder made here is set to 0777 and every download goes
    to a per-process .partial, so any agent user can add a tool and a race
    ends with one good file. If a folder made earlier by another user is not
    writable, one warning goes to stderr and ~/.cache/ci-tools is used.
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
import shutil
import subprocess
import sys
import tarfile
import tempfile
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


_FALLBACK: Path | None = None  # per-user cache, set when a shared folder is not writable (DL194)


def _home_cache() -> Path:
    return Path.home() / ".cache" / "ci-tools"


def _use_fallback(why: Path) -> None:
    global _FALLBACK
    _FALLBACK = _home_cache()
    print(f"ci_tool: {why} is not writable; using the per-user cache {_FALLBACK}", file=sys.stderr)


def _is_shared(path: Path) -> bool:
    """True for a world-writable cache root (the pool's /ci-tools). Never on Windows (DL194)."""
    if os.name == "nt":
        return False
    try:
        return bool(path.stat().st_mode & 0o002)
    except OSError:
        return False


def _mkdirs(path: Path, root: Path) -> None:
    """Make path and its parents. In a shared cache each new folder is 0777, so any agent user can add to it (DL194)."""
    path.mkdir(parents=True, exist_ok=True)
    if not _is_shared(root):
        return
    p = path
    while p != root and root in p.parents:
        try:
            if p.stat().st_uid == os.getuid() and p.stat().st_mode & 0o777 != 0o777:
                os.chmod(p, 0o777)
        except OSError:
            pass
        p = p.parent


def cache_dir() -> Path:
    if _FALLBACK is not None:
        _FALLBACK.mkdir(parents=True, exist_ok=True)
        return _FALLBACK
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
    root = cache_dir()
    _mkdirs(target.parent, root)
    if not os.access(target.parent, os.W_OK | os.X_OK):
        # A folder made by another user before DL194 (0755): use a per-user cache.
        _use_fallback(target.parent)
        target = cache_dir().joinpath(*parts)
        if target.is_file() and sha256_of(target) == sha256:
            return target.resolve()
        _mkdirs(target.parent, cache_dir())
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
    if _FALLBACK is None and not os.access(archive.parent, os.W_OK | os.X_OK):
        _use_fallback(archive.parent)
        archive = fetch(url, sha, f"gitleaks/{version}/{archive_name}")
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


def _pin(name: str, plat: str, pin_path=None) -> tuple[dict, dict]:
    """Return (tool pin, platform entry) from tools.json, or raise ToolError."""
    pin_file = Path(pin_path or os.environ.get("CI_TOOLS_JSON") or Path(__file__).resolve().parent / "tools.json")
    try:
        data = json.loads(pin_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"cannot read {pin_file}: {exc}")
    tool_pin = data.get(name) if isinstance(data, dict) else None
    if not isinstance(tool_pin, dict) or "version" not in tool_pin:
        raise ToolError(f"{pin_file} has no pin for {name}. Run: python3 scripts/delivery/tools_pin.py")
    entry = (tool_pin.get("platforms") or {}).get(plat)
    if not isinstance(entry, dict) or not entry.get("url") or not entry.get("sha256"):
        raise ToolError(f"{pin_file} has no pinned URL and SHA-256 for {name} on {plat}")
    return tool_pin, entry


def _safe_unpack(archive: Path, dest: Path, keep_modes: bool = False) -> None:
    name = archive.name.lower()
    root = dest.resolve()

    def inside(member: str) -> None:
        if not (root / member).resolve().is_relative_to(root):
            raise ToolError(f"{archive} has an unsafe path: {member}")

    if name.endswith((".zip", ".whl")):
        with zipfile.ZipFile(archive) as z:
            for m in z.namelist():
                inside(m)
            z.extractall(dest)
            if keep_modes:  # a wheel keeps the exec bit only in the zip entry
                for i in z.infolist():
                    mode = (i.external_attr >> 16) & 0o777
                    if mode and not i.is_dir():
                        os.chmod(dest / i.filename, mode | 0o600)
        return
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            inside(m.name)
            if m.issym() or m.islnk():
                target = m.linkname if m.islnk() else os.path.join(os.path.dirname(m.name), m.linkname)
                inside(target)
            if m.isdev():
                raise ToolError(f"{archive} has a device file: {m.name}")
        t.extractall(dest)


def _fresh_dir(final: Path) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"{final.name}.", suffix=".partial", dir=final.parent))


def _install_dir(final: Path, build) -> Path:
    """Run build(tmp_dir) into a unique temp folder, then rename it to final."""
    if final.is_dir():
        return final
    tmp = _fresh_dir(final)
    try:
        build(tmp)
        os.chmod(tmp, 0o777 if _is_shared(cache_dir()) else 0o755)  # mkdtemp makes 0700 (DL194)
        try:
            os.replace(tmp, final)
        except OSError:
            if not final.is_dir():  # lost a race on Windows is fine; anything else is not
                raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return final


def _exe(base: str, plat: str) -> str:
    return base + ".exe" if plat.startswith("windows") and not base.endswith(".exe") else base


def _prepared(base: Path, plat: str, kind: str, entry: dict, name: str) -> bool:
    """True when the tool's prepared output already exists under base."""
    if kind == "file":
        return (base / plat / _exe(entry.get("bin") or name, plat)).is_file()
    return (base / (f"unpacked-{plat}" if kind in ("archive", "wheel") else f"root-{plat}")).is_dir()


def tool_dir(name: str, plat: str) -> tuple[Path, Path, dict]:
    """Fetch and prepare a pinned tool. Return (bin folder, default bin file, entry)."""
    tool_pin, entry = _pin(name, plat)
    version = str(tool_pin["version"])
    kind = entry.get("kind") or tool_pin.get("kind") or "archive"
    fname = entry.get("file") or entry["url"].rsplit("/", 1)[-1]
    archive = fetch(entry["url"], entry["sha256"], f"{name}/{version}/{fname}")
    base = archive.parent
    if _FALLBACK is None and not os.access(base, os.W_OK | os.X_OK) and not _prepared(base, plat, kind, entry, name):
        _use_fallback(base)
        archive = fetch(entry["url"], entry["sha256"], f"{name}/{version}/{fname}")
        base = archive.parent
    if kind == "file":
        # Keep the exact file name: some tools (rustup-init) read argv[0].
        out = base / plat / _exe(entry.get("bin") or name, plat)
        if not out.is_file():
            _mkdirs(out.parent, cache_dir())
            tmp = out.with_name(f"{out.name}.{os.getpid()}.partial")
            try:
                shutil.copyfile(archive, tmp)
                os.chmod(tmp, 0o755)
                os.replace(tmp, out)
            except OSError as exc:
                raise ToolError(f"cannot prepare {name}: {exc}")
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return out.parent, out, entry
    if kind in ("archive", "wheel"):
        def build(tmp: Path) -> None:
            _safe_unpack(archive, tmp, keep_modes=(kind == "wheel"))
        try:
            root = _install_dir(base / f"unpacked-{plat}", build)
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            raise ToolError(f"cannot unpack {archive}: {exc}")
        bin_dir = root / entry.get("bin_dir", ".")
        default = bin_dir / _exe(Path(entry.get("bin") or name).name, plat)
        return bin_dir, default, entry
    if kind == "crate":
        cargo = os.environ.get("CI_TOOL_CARGO", "cargo")

        def build(tmp: Path) -> None:
            src = tmp / "src"
            src.mkdir()
            _safe_unpack(archive, src)
            crate_dirs = [d for d in src.iterdir() if d.is_dir()]
            if len(crate_dirs) != 1:
                raise ToolError(f"{archive} does not hold one crate folder")
            try:
                done = subprocess.run(
                    [cargo, "install", "--locked", "--path", str(crate_dirs[0]), "--root", str(tmp / "root")],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            except OSError as exc:
                raise ToolError(f"cannot run {cargo}: {exc}")
            if done.returncode != 0:
                raise ToolError(f"cargo install {name} {version} failed: {done.stdout[-400:]}")
            shutil.rmtree(src, ignore_errors=True)
        try:
            root = _install_dir(base / f"root-{plat}", build)
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            raise ToolError(f"cannot build {name}: {exc}")
        bin_dir = root / "root" / "bin" if (root / "root").is_dir() else root / "bin"
        return bin_dir, bin_dir / _exe(entry.get("bin") or name, plat), entry
    raise ToolError(f"{name} has unknown kind {kind!r}")


def cached_tool(name: str, plat: str, exe: str | None = None, pin_path=None) -> Path | None:
    """Where `tool` puts a tool's file, if it is already in the cache. Downloads nothing. None when it is not there (DL188)."""
    try:
        tool_pin, entry = _pin(name, plat, pin_path)
    except ToolError:
        return None
    base = cache_dir() / name / str(tool_pin["version"])
    kind = entry.get("kind") or tool_pin.get("kind") or "archive"
    if kind == "file":
        path = base / f"{plat}-{_exe(entry.get('bin') or name, plat)}"
    elif kind in ("archive", "wheel"):
        bin_dir = base / f"unpacked-{plat}" / entry.get("bin_dir", ".")
        path = bin_dir / _exe(exe or Path(entry.get("bin") or name).name, plat)
    else:
        root = base / f"root-{plat}"
        bin_dir = root / "root" / "bin" if (root / "root").is_dir() else root / "bin"
        path = bin_dir / _exe(exe or entry.get("bin") or name, plat)
    return path if path.exists() else None


def tool(name: str, plat: str, exe: str | None = None) -> Path:
    """Path of a pinned tool's bin file (or of `exe` in its bin folder)."""
    if name == "gitleaks":
        return gitleaks(plat)
    bin_dir, default, _ = tool_dir(name, plat)
    path = bin_dir / _exe(exe, plat) if exe else default
    if not path.exists():
        raise ToolError(f"{name} has no {path.name} in {bin_dir}")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ci_tool.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("url")
    f.add_argument("--sha256", required=True)
    f.add_argument("--name", required=True)
    g = sub.add_parser("gitleaks")
    g.add_argument("--platform", choices=PLATFORMS, default=None)
    t = sub.add_parser("tool")
    t.add_argument("name")
    t.add_argument("--platform", choices=PLATFORMS, default=None)
    t.add_argument("--exe", default=None)
    t.add_argument("--dir", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        if args.cmd == "fetch":
            path = fetch(args.url, args.sha256, args.name)
        elif args.cmd == "tool":
            plat = args.platform or current_platform()
            if args.dir:
                path = tool_dir(args.name, plat)[0] if args.name != "gitleaks" else gitleaks(plat).parent
            else:
                path = tool(args.name, plat, args.exe)
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
