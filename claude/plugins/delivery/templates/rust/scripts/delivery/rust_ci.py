#!/usr/bin/env python3
"""DS200: Rust CI helper (toolchain, linker env, advisory check, isolated gate run, smoke).

Subcommands:
  toolchain            install the exact channel in rust-toolchain.toml with the pinned rustup-init
  env [--format F]     print the linker environment (F: sh, cmd, json; default json)
  deny                 cargo-deny with a cached RustSec clone (warn up to 7 days old, fail after)
  run [--] CMD...      run CMD with the linker env and, when gate.json says
                       "toolchain-isolated" is true (default false, DS206), without system compilers on PATH
  fmt | check | clippy | test [ARGS...]
                       cargo fmt/check/clippy/test through `run`; RUST_CRATES (package names) limits
                       them to `-p a -p b`, else the whole workspace (DL295)
  smoke                build each binary in smoke.json "binaries" in debug and run --version

Exit codes: 0 ok, 1 failure, 2 usage. Standard library only. Tools come from
`ci_tool.py tool <name>`; nothing here commits, pushes or merges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ADVISORY_WARN_DAYS = 7
ADVISORY_URL = "https://github.com/RustSec/advisory-db.git"
COMPILERS = ("cc", "gcc", "clang", "ld")
WIN_TARGET = "x86_64-pc-windows-msvc"
CC_NOT_FOUND = "linker cc not found"


class RustCiError(Exception):
    pass


def _ci_tool():
    import ci_tool
    return ci_tool


def cache_dir() -> Path:
    return _ci_tool().cache_dir()


def root_dir() -> Path:
    return Path(os.environ.get("RUST_CI_ROOT") or os.getcwd())


def tool_path(name: str, exe: str | None = None) -> Path:
    """Path of a pinned tool, through ci_tool.py (in process, so tests can fake the pins)."""
    ci = _ci_tool()
    try:
        return ci.tool(name, ci.current_platform(), exe)
    except ci.ToolError as exc:
        raise RustCiError(str(exc)) from None


def tool_pinned(name: str) -> bool:
    ci = _ci_tool()
    try:
        ci._pin(name, ci.current_platform())
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# rust-toolchain.toml
# --------------------------------------------------------------------------

def read_toolchain(root: Path) -> tuple[str, list[str]]:
    path = root / "rust-toolchain.toml"
    if not path.exists():
        raise RustCiError("rust-toolchain.toml is missing. Add [toolchain] channel = \"1.90.0\"")
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^\s*channel\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise RustCiError("rust-toolchain.toml has no channel")
    channel = m.group(1)
    if not re.fullmatch(r"\d+\.\d+\.\d+", channel):
        raise RustCiError("rust-toolchain.toml channel is %r, not an exact version such as 1.90.0" % channel)
    targets: list[str] = []
    t = re.search(r"^\s*targets\s*=\s*\[(.*?)\]", text, re.M | re.S)
    if t:
        targets = re.findall(r'"([^"]+)"', t.group(1))
    return channel, targets


def host_triple() -> str:
    arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "win32":
        return arch + "-pc-windows-msvc"
    if sys.platform == "darwin":
        return arch + "-apple-darwin"
    return arch + "-unknown-linux-gnu"


def gate_cfg(root: Path) -> dict:
    for p in (root / "scripts" / "delivery" / "gate.json", HERE / "gate.json"):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def isolated(root: Path) -> bool:
    return gate_cfg(root).get("toolchain-isolated", False) is True


# --------------------------------------------------------------------------
# toolchain
# --------------------------------------------------------------------------

def cmd_toolchain(root: Path) -> int:
    channel, targets = read_toolchain(root)
    init = tool_path("rustup-init")
    args = [str(init), "-y", "--no-modify-path", "--profile", "minimal", "--default-toolchain", channel]
    for t in targets:
        args += ["--target", t]
    print("rust_ci: installing Rust %s" % channel)
    return subprocess.run(args).returncode


# --------------------------------------------------------------------------
# linker environment
# --------------------------------------------------------------------------

def _write_zig_wrapper(zig: Path) -> Path:
    d = cache_dir() / "zig-wrap"
    d.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        w = d / "zig-cc.cmd"
        w.write_text('@echo off\r\n"%s" cc %%*\r\n' % zig, encoding="utf-8")
    else:
        w = d / "zig-cc"
        w.write_text('#!/bin/sh\nexec "%s" cc "$@"\n' % zig, encoding="utf-8")
        w.chmod(0o755)
    return w


def host_linker() -> tuple[str, str | None]:
    """(linker path, warning). System cc first (DS206), then pinned Zig, else RustCiError."""
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc:
        return cc, None
    if tool_pinned("zig"):
        try:
            return str(_write_zig_wrapper(tool_path("zig"))), None
        except RustCiError as exc:
            raise RustCiError("pinned zig could not be used: %s" % exc) from None
    raise RustCiError("%s. Fix: install a C compiler (sudo apt-get install -y build-essential pkg-config), "
                      "or pin Zig from the ziglang wheel on PyPI: python3 scripts/delivery/tools_pin.py entry zig ..." % CC_NOT_FOUND)


def build_env(root: Path) -> tuple[dict[str, str], list[str]]:
    env: dict[str, str] = {}
    warns: list[str] = []
    try:
        _, targets = read_toolchain(root)
    except RustCiError:
        targets = []
    host = host_triple()
    key = lambda t: "CARGO_TARGET_%s_LINKER" % t.upper().replace("-", "_")  # noqa: E731
    if "windows" not in host:
        linker, warn = host_linker()
        env[key(host)] = linker
        if warn:
            warns.append(warn)
    if any("windows-msvc" in t for t in targets) and "windows" not in host:
        bindir = Path(tool_path("llvm", "lld-link")).parent
        llvm = {"lld-link": tool_path("llvm", "lld-link"), "clang-cl": tool_path("llvm", "clang-cl"),
                "llvm-lib": tool_path("llvm", "llvm-lib")}
        env[key(WIN_TARGET)] = str(llvm["lld-link"])
        env["CC_x86_64_pc_windows_msvc"] = str(llvm["clang-cl"])
        env["CXX_x86_64_pc_windows_msvc"] = str(llvm["clang-cl"])
        env["AR_x86_64_pc_windows_msvc"] = str(llvm["llvm-lib"])
        env["RUST_CI_LLVM_BIN"] = str(bindir)
    env.update(target_cache_env(root))
    return env, warns


# --------------------------------------------------------------------------
# persistent per-runner target cache (DL295)
# --------------------------------------------------------------------------

def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", text) or "x"


def cache_key(root: Path) -> str:
    channel, _ = read_toolchain(root)
    try:
        digest = hashlib.sha256((root / "Cargo.lock").read_bytes()).hexdigest()[:16]
    except OSError:
        digest = "nolock"
    return _safe("%s-%s" % (channel, digest))


def _tree_size(path: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def _key_in_use_win(key: Path) -> bool:
    """DL342: Windows check with msvcrt byte-range locks. Anything unclear counts as in use."""
    try:
        import msvcrt
    except ImportError:
        return True
    for lock in key.glob("*/.cargo-lock"):
        try:
            fd = os.open(str(lock), os.O_RDWR)
        except OSError:
            return True
        try:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)
    return False


def key_in_use(key: Path) -> bool:
    """True when a cargo process holds <key>/*/.cargo-lock. Where neither fcntl nor msvcrt exists every key is in use."""
    try:
        import fcntl
    except ImportError:
        return _key_in_use_win(key)
    for lock in key.glob("*/.cargo-lock"):
        try:
            fd = os.open(str(lock), os.O_RDWR)
        except OSError:
            return True
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    return False


def prune_target_cache(runner_dir: Path, current: Path, cap_bytes: int) -> list[str]:
    """Delete the oldest keys while the runner's keys exceed the cap. Returns the removed key names.

    Never the current key, never the newest other key, never a key in use."""
    keys = [p for p in runner_dir.iterdir() if p.is_dir()]
    sizes = {p: _tree_size(p) for p in keys}
    total = sum(sizes.values())
    removed: list[str] = []
    others = sorted((p for p in keys if p != current), key=lambda p: p.stat().st_mtime)
    keep_newest = others[-1] if others else None
    for p in others:
        if total <= cap_bytes:
            break
        if p == keep_newest or key_in_use(p):
            continue
        shutil.rmtree(p, ignore_errors=True)
        total -= sizes[p]
        removed.append(p.name)
    return removed


def _clear_children(path: Path) -> None:
    for child in list(path.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def enforce_cap(runner_dir: Path, current: Path, cap_bytes: int) -> list[str]:
    """DL342: make the runner's keys total at most the cap, except a key in use. Run after prune_target_cache.

    1. The newest other key goes when the total is still over the cap.
    2. The current key goes through two steps when it alone is over the cap: its incremental/ folders, then all its content.
    Returns one text per removal, naming what went and why."""
    msgs: list[str] = []
    cap_gb = cap_bytes / 1024 ** 3
    others = sorted((p for p in runner_dir.iterdir() if p.is_dir() and p != current), key=lambda p: p.stat().st_mtime)
    total = _tree_size(current) + sum(_tree_size(p) for p in others)
    if total > cap_bytes and others and not key_in_use(others[-1]):
        size = _tree_size(others[-1])
        shutil.rmtree(others[-1], ignore_errors=True)
        total -= size
        msgs.append("key %s (%.2f GB) over the %.0f GB cap" % (others[-1].name, size / 1024 ** 3, cap_gb))
    size = _tree_size(current)
    if size > cap_bytes and not key_in_use(current):
        for inc in current.glob("*/incremental"):
            shutil.rmtree(inc, ignore_errors=True)
        after = _tree_size(current)
        what = "incremental folders of %s" % current.name
        if after > cap_bytes:
            _clear_children(current)
            after = _tree_size(current)
            what = "all content of %s" % current.name
        msgs.append("%s (%.2f -> %.2f GB), the key alone was over the %.0f GB cap"
                    % (what, size / 1024 ** 3, after / 1024 ** 3, cap_gb))
    return msgs


def target_cache_env(root: Path) -> dict[str, str]:
    """{'CARGO_TARGET_DIR': path} for the persistent cache, or {} when it is off or fails."""
    if os.environ.get("CARGO_TARGET_DIR") or os.environ.get("DELIVERY_NO_TARGET_CACHE") == "1":
        return {}
    try:
        runner = _safe(os.environ.get("RUNNER_NAME") or "local")
        runner_dir = cache_dir() / "cargo-target" / runner
        key = runner_dir / cache_key(root)
        key.mkdir(parents=True, exist_ok=True)
        os.utime(key, None)
        cap = int(float(os.environ.get("RUST_TARGET_CAP_GB") or 40) * 1024 ** 3)
        removed = prune_target_cache(runner_dir, key, cap)
        cleaned = enforce_cap(runner_dir, key, cap)
    except (OSError, ValueError, ImportError, RustCiError) as exc:  # ImportError: no ci_tool next to this script
        print("rust_ci: build cache unavailable (%s); using target/" % exc, file=sys.stderr)
        return {}
    print("rust_ci: build cache %s (pruned: %s)" % (key, ", ".join(removed) or "none"), file=sys.stderr)
    if cleaned:
        print("rust_ci: cache cap: removed %s" % "; ".join(cleaned), file=sys.stderr)
    link_target(root, key)
    return {"CARGO_TARGET_DIR": str(key), "DELIVERY_RUST_TARGET": str(key)}


def _is_link(path: Path) -> bool:
    """True for a symlink or a Windows junction."""
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path, "is_junction", lambda: False)())
    except OSError:
        return False


def _make_link(link: Path, dest: Path) -> None:
    if os.name == "nt":
        try:
            import _winapi  # type: ignore
            _winapi.CreateJunction(str(dest), str(link))
            return
        except (ImportError, AttributeError):
            pass
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(dest)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError((r.stderr or r.stdout or "mklink failed").strip())
    else:
        os.symlink(str(dest), str(link), target_is_directory=True)


def _remove_link(link: Path) -> None:
    if os.name == "nt" and not link.is_symlink():
        os.rmdir(str(link))  # removes a junction, never its contents
    else:
        link.unlink()


def _exclude_link(root: Path) -> None:
    """Hide the link from git status: `target/` in .gitignore does not match a link, `/target` does."""
    info = root / ".git" / "info"
    try:
        if not info.is_dir():
            return
        ex = info / "exclude"
        text = ex.read_text(encoding="utf-8") if ex.exists() else ""
        if "/target" not in [ln.strip() for ln in text.splitlines()]:
            ex.write_text(text + ("" if not text or text.endswith("\n") else "\n") + "/target\n", encoding="utf-8")
    except OSError:
        pass


def link_target(root: Path, cache: Path) -> bool:
    """Point <root>/target at the cache folder (DL329). A real folder is kept; a failure only warns."""
    link = root / "target"
    try:
        if _is_link(link):
            _remove_link(link)
        elif os.path.lexists(str(link)):
            print("rust_ci: %s is a real folder; bins live in %s" % (link, cache), file=sys.stderr)
            return False
        _make_link(link, cache)
        _exclude_link(root)
        return True
    except OSError as exc:
        print("rust_ci: could not link %s to %s (%s); bins live in %s" % (link, cache, exc, cache),
              file=sys.stderr)
        return False


def crate_args(flag: str = "--workspace") -> list[str]:
    """`-p a -p b` from RUST_CRATES, else `flag` (whole workspace)."""
    names = (os.environ.get("RUST_CRATES") or "").split()
    if not names:
        return [flag]
    return [x for n in names for x in ("-p", n)]


def cmd_env(root: Path, fmt: str) -> int:
    env, warns = build_env(root)
    for w in warns:
        print("rust_ci: warning: " + w, file=sys.stderr)
    if fmt == "json":
        print(json.dumps(env, indent=2, sort_keys=True))
    elif fmt == "cmd":
        for k, v in sorted(env.items()):
            print("set %s=%s" % (k, v))
    else:
        for k, v in sorted(env.items()):
            print("export %s='%s'" % (k, v.replace("'", "'\\''")))
    return 0


# --------------------------------------------------------------------------
# gate run (system compilers removed from PATH)
# --------------------------------------------------------------------------

def strip_path(path: str, keep: list[str] | None = None) -> str:
    """PATH without folders that hold a system compiler (cc, gcc, clang, ld).

    A folder that holds cargo or rustc is kept, as is any folder in `keep`."""
    exts = [""] + (os.environ.get("PATHEXT", ".EXE;.CMD;.BAT").lower().split(";") if os.name == "nt" else [])
    keep_set = {os.path.normcase(k) for k in (keep or [])}
    out = []
    for d in path.split(os.pathsep):
        if not d or os.path.normcase(d) in keep_set:
            out.append(d) if d else None
            continue
        has_tool = any(os.path.exists(os.path.join(d, c + e)) for c in ("cargo", "rustc", "rustup") for e in exts)
        has_cc = any(os.path.exists(os.path.join(d, c + e)) for c in COMPILERS for e in exts)
        if has_cc and not has_tool:
            continue
        out.append(d)
    return os.pathsep.join(out)


def cmd_run(root: Path, command: list[str]) -> int:
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("rust_ci: run needs a command", file=sys.stderr)
        return 2
    env, warns = build_env(root)  # resolves cc before PATH is cleaned
    for w in warns:
        print("rust_ci: warning: " + w, file=sys.stderr)
    full = {**os.environ, **env}
    if isolated(root):
        keep = [env["RUST_CI_LLVM_BIN"]] if "RUST_CI_LLVM_BIN" in env else []  # linkers are set by absolute path
        full["PATH"] = strip_path(full.get("PATH", ""), keep)
    # DL301: Windows resolves the program with this process's PATH, not env's; resolve it on the job PATH first.
    found = shutil.which(command[0], path=full.get("PATH"))
    if found:
        command = [found, *command[1:]]
    return subprocess.run(command, cwd=root, env=full).returncode


def cmd_cargo(root: Path, verb: str, extra: list[str]) -> int:
    if extra and extra[0] == "--":
        extra = extra[1:]
    cargo = _cargo()
    if verb == "fmt":
        names = (os.environ.get("RUST_CRATES") or "").split()
        scope = [x for n in names for x in ("-p", n)] if names else ["--all"]
        cmd = [cargo, "fmt"] + scope + ["--check"] + extra
    elif verb == "check":
        cmd = [cargo, "check", "--locked"] + crate_args() + ["--all-targets"] + extra
    elif verb == "clippy":
        cmd = [cargo, "clippy", "--locked"] + crate_args() + ["--all-targets"] + extra + ["--", "-D", "warnings"]
    else:
        cmd = [cargo, "test", "--locked"] + crate_args() + extra
    return cmd_run(root, cmd)


# --------------------------------------------------------------------------
# cargo-deny with a cached advisory database
# --------------------------------------------------------------------------

def advisory_dir() -> Path:
    return cache_dir() / "advisory-db"


def cache_age_days(path: Path) -> float | None:
    stamp = path / ".rust_ci_fetched"
    if not path.is_dir():
        return None
    try:
        return (time.time() - (stamp if stamp.exists() else path).stat().st_mtime) / 86400
    except OSError:
        return None


def summary(line: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _cargo() -> str:
    return os.environ.get("RUST_CI_CARGO") or "cargo"


def deny_toml_copy(root: Path, db: Path) -> Path:
    """A generated copy of deny.toml with db-path set. The committed file is never edited."""
    src = root / "deny.toml"
    text = src.read_text(encoding="utf-8") if src.exists() else ""
    m = re.search(r"^\[advisories\]\s*$", text, re.M)
    line = 'db-path = "%s"\ndb-urls = ["%s"]\n' % (str(db).replace("\\", "/"), ADVISORY_URL)
    text = re.sub(r"^\s*db-path\s*=.*\n", "", text, flags=re.M)
    if m:
        text = re.sub(r"^\[advisories\]\s*$", "[advisories]\n" + line.rstrip("\n"), text, count=1, flags=re.M)
    else:
        text += "\n[advisories]\n" + line
    out = cache_dir() / "deny.generated.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def cmd_deny(root: Path) -> int:
    db = advisory_dir()
    db.mkdir(parents=True, exist_ok=True)
    cfg = deny_toml_copy(root, db)
    cargo = _cargo()
    fetch = subprocess.run([cargo, "deny", "--config", str(cfg), "fetch"], cwd=root)
    if fetch.returncode == 0:
        (db / ".rust_ci_fetched").write_text(str(time.time()), encoding="utf-8")
    else:
        age = cache_age_days(db) if (db / ".rust_ci_fetched").exists() else None
        if age is None:
            print("rust_ci: advisory database fetch failed and there is no cached copy. "
                  "Run once with network access: python3 scripts/delivery/rust_ci.py deny", file=sys.stderr)
            summary("**cargo-deny: FAILED.** The advisory database could not be fetched and there is no cache.")
            return 1
        if age > ADVISORY_WARN_DAYS:
            print("rust_ci: advisory database fetch failed and the cache is %.0f days old (limit %d). "
                  "Refresh it with network access." % (age, ADVISORY_WARN_DAYS), file=sys.stderr)
            summary("**cargo-deny: FAILED.** Advisory cache is %.0f days old (limit %d)." % (age, ADVISORY_WARN_DAYS))
            return 1
        msg = "advisory database fetch failed; using the cache, %.1f days old (fails after %d days)" % (
            age, ADVISORY_WARN_DAYS)
        print("rust_ci: warning: " + msg, file=sys.stderr)
        summary("**cargo-deny warning:** " + msg + ".")
    # cargo-deny 0.20.2 has no check-only fetch flag. `--offline` is a top-level flag and must come
    # before the subcommand; it stops the check from fetching the advisory database.
    return subprocess.run([cargo, "deny", "--config", str(cfg), "--offline", "check"], cwd=root).returncode


# --------------------------------------------------------------------------
# smoke
# --------------------------------------------------------------------------

def cmd_smoke(root: Path) -> int:
    path = root / "scripts" / "delivery" / "smoke.json"
    try:
        smoke = json.loads(path.read_text(encoding="utf-8")).get("smoke", {})
    except (OSError, ValueError) as exc:
        print("rust_ci: cannot read %s: %s" % (path, exc), file=sys.stderr)
        return 1
    bins = smoke.get("binaries") or []
    if not bins:
        print("rust_ci: smoke: no binaries declared; nothing to build")
        return 0
    exe = ".exe" if os.name == "nt" else ""
    for b in bins:
        name = b if isinstance(b, str) else b.get("bin", "")
        if not name:
            print("rust_ci: smoke: a binary entry has no name", file=sys.stderr)
            return 1
        if cmd_run(root, [_cargo(), "build", "--locked", "--bin", name]) != 0:
            print("rust_ci: smoke: FAILED, build of %s failed" % name, file=sys.stderr)
            return 1
        target = build_env(root)[0].get("CARGO_TARGET_DIR") or os.environ.get("CARGO_TARGET_DIR") or str(root / "target")
        res = subprocess.run([os.path.join(target, "debug", name + exe), "--version"],
                             capture_output=True, text=True)
        if res.returncode != 0:
            print("rust_ci: smoke: FAILED, %s --version exited %d" % (name, res.returncode), file=sys.stderr)
            return 1
        print("rust_ci: smoke: %s: %s" % (name, res.stdout.strip()))
    print("rust_ci: smoke: passed (%d binar%s)" % (len(bins), "y" if len(bins) == 1 else "ies"))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rust_ci.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("toolchain")
    e = sub.add_parser("env")
    e.add_argument("--format", choices=("sh", "cmd", "json"), default="json")
    sub.add_parser("deny")
    r = sub.add_parser("run")
    r.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("smoke")
    for verb in ("fmt", "check", "clippy", "test"):
        sub.add_parser(verb).add_argument("extra", nargs=argparse.REMAINDER)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    root = root_dir()
    try:
        if args.cmd == "toolchain":
            return cmd_toolchain(root)
        if args.cmd == "env":
            return cmd_env(root, args.format)
        if args.cmd == "deny":
            return cmd_deny(root)
        if args.cmd == "run":
            return cmd_run(root, args.command)
        if args.cmd in ("fmt", "check", "clippy", "test"):
            return cmd_cargo(root, args.cmd, args.extra)
        return cmd_smoke(root)
    except RustCiError as exc:
        print("rust_ci: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
