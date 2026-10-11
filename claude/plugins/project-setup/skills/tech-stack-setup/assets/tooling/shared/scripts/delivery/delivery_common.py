#!/usr/bin/env python3
"""Shared helpers for the delivery scripts (see CONTRACT.md).

Python 3.11+, standard library only. Imported by branch_gate.py, gate_verify.py,
fast_guards.py and join.py; not run directly.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 11):  # tomllib, and the contract, need 3.11
    sys.stderr.write(
        "delivery scripts need Python 3.11 or newer (found %s). "
        "Run scripts/delivery/agent_setup.sh.\n" % sys.version.split()[0]
    )
    sys.exit(2)

import datetime
import fnmatch
import glob
import json
import os
import posixpath
import re
import signal
import subprocess
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = 1
TOOL_VERSION = 2

EXIT_OK = 0
EXIT_FAIL = 1  # checks failed, or a result is not trusted
EXIT_USAGE = 2  # usage or configuration error; could not decide
EXIT_CONFLICT = 3  # join stopped at a conflict
EXIT_TIMEOUT = 4

DEFAULT_TIMEOUT_MINUTES = 30  # one branch_gate.py run, setup included
FAST_STEP_TIMEOUT_MINUTES = 5  # one fast_guards.py step
TAIL_LINES = 40  # lines of a failed step printed after the summary
SETUP_STEP = "setup"  # reserved step name: the gate.json "setup" commands

SCOPES = ("always", "changed", "changed+dependents", "ui-changed")
PACKAGE_KINDS = ("pnpm-workspace", "go-modules", "cargo-workspace", "dotnet-sln")

DELIVERY_DIR = ".delivery"
LOG_DIR = ".delivery/logs"  # one <step>.log per step, combined stdout and stderr
FAST_LOG_DIR = ".delivery/logs/pre-push"  # fast_guards.py keeps its own, so a push never overwrites a gate log
GATE_RESULT_PATH = ".delivery/gate-result.json"
JOIN_RESULT_PATH = ".delivery/join-result.json"
GATE_JSON_PATH = "scripts/delivery/gate.json"
RESULT_REF_PREFIX = "refs/gate-results/"
# Where a fetched copy of a remote's result ref is kept locally. Deliberately
# not under refs/gate-results/, so a fetch can never be pushed back by accident.
FETCHED_REF_PREFIX = "refs/gate-results-fetched/"
RESULT_FILE_IN_REF = "gate-result.json"

# Lockfiles join.py may resolve itself (take the integration branch's version,
# re-run setup). A gate.json may add to this with a "lockfiles" list.
DEFAULT_LOCKFILES = (
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "go.sum",
    "go.work.sum",
    "Cargo.lock",
    "packages.lock.json",
)

_SKIP_DIRS = {".git", "node_modules", ".delivery", "vendor", "target", "bin", "obj", "testdata"}


class DeliveryError(Exception):
    """A usage or configuration problem. Carries the exit code to use."""

    def __init__(self, message: str, code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code


def eprint(*parts: object) -> None:
    print(*parts, file=sys.stderr, flush=True)


def posix(path: object) -> str:
    return str(path).replace("\\", "/")


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------

_ident_env: dict[str, str] | None = None


def git_env() -> dict[str, str]:
    """Environment for git commands that create commits. A machine with no
    user.name/user.email (a fresh agent sandbox) still gets a valid identity."""
    global _ident_env
    if _ident_env is None:
        env = os.environ.copy()
        for key, suffix, fallback in (
            ("user.name", "NAME", "delivery-gate"),
            ("user.email", "EMAIL", "delivery-gate@localhost"),
        ):
            have = subprocess.run(
                ["git", "config", key], capture_output=True, text=True, check=False
            ).stdout.strip()
            if not have:
                env.setdefault("GIT_AUTHOR_" + suffix, fallback)
                env.setdefault("GIT_COMMITTER_" + suffix, fallback)
        _ident_env = env
    return _ident_env


def run_git(
    args: list[str],
    cwd: Path | str | None = None,
    check: bool = True,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run git with an argument list. Text in and out, UTF-8, POSIX newlines."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            input=input_text.encode("utf-8") if input_text is not None else None,
            capture_output=True,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        raise DeliveryError("git is not installed or not on PATH") from None
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    result = subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    if check and proc.returncode != 0:
        raise DeliveryError("git %s failed: %s" % (" ".join(args[:3]), (err or out).strip()))
    return result


def git(args: list[str], cwd: Path | str | None = None, **kw) -> str:
    return run_git(args, cwd=cwd, **kw).stdout.strip()


def rev(ref: str, cwd: Path | str | None = None) -> str | None:
    """The commit a ref names, or None."""
    p = run_git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"], cwd=cwd, check=False)
    return p.stdout.strip() or None if p.returncode == 0 else None


def is_ancestor(ancestor: str, descendant: str, cwd: Path | str | None = None) -> bool:
    return run_git(
        ["merge-base", "--is-ancestor", ancestor, descendant], cwd=cwd, check=False
    ).returncode == 0


def repo_root() -> Path:
    p = run_git(["rev-parse", "--show-toplevel"], check=False)
    if p.returncode != 0:
        raise DeliveryError("not inside a git repository")
    return Path(p.stdout.strip())


def current_branch(cwd: Path | str | None = None) -> str:
    """The checked-out branch name, or '' when HEAD is detached."""
    return git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=cwd, check=False)


def remotes(cwd: Path | str | None = None) -> list[str]:
    return git(["remote"], cwd=cwd, check=False).split()


def remote_of(ref: str, default: str = "origin", cwd: Path | str | None = None) -> str:
    """The remote a ref like 'origin/main' belongs to; `default` otherwise."""
    head = ref.split("/", 1)[0]
    return head if "/" in ref and head in remotes(cwd) else default


def dirty_paths(root: Path) -> list[str]:
    """Modified, staged or untracked paths, ignoring the .delivery/ results dir."""
    out = git(["status", "--porcelain", "--untracked-files=normal"], cwd=root)
    paths = []
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if path == DELIVERY_DIR or path.startswith(DELIVERY_DIR + "/"):
            continue
        if "__pycache__" in path.split("/"):  # bytecode of these very scripts
            continue
        paths.append(path)
    return paths


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------

def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# gate.json
# --------------------------------------------------------------------------

def _str_list(cfg: dict, key: str, where: str) -> list[str]:
    value = cfg.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise DeliveryError("%s: '%s' must be a list of strings" % (where, key))
    return value


def load_gate(root: Path) -> dict:
    """Read and validate scripts/delivery/gate.json. Fills defaults."""
    path = root / GATE_JSON_PATH
    if not path.is_file():
        raise DeliveryError("%s not found" % GATE_JSON_PATH)
    try:
        cfg = read_json(path)
    except (OSError, ValueError) as exc:
        raise DeliveryError("%s is not valid JSON: %s" % (GATE_JSON_PATH, exc)) from None
    where = GATE_JSON_PATH
    if not isinstance(cfg, dict) or cfg.get("schema") != SCHEMA:
        raise DeliveryError("%s: expected an object with \"schema\": %d" % (where, SCHEMA))
    cfg.setdefault("default_branch", "main")
    if not isinstance(cfg["default_branch"], str) or not cfg["default_branch"]:
        raise DeliveryError("%s: 'default_branch' must be a non-empty string" % where)
    for key in ("setup", "widen_on", "ui_paths", "lockfiles"):
        cfg[key] = _str_list(cfg, key, where)
    cfg.setdefault("specs", ["docs/specs/*.md"])
    cfg.setdefault("release_branches", ["*-integration", "release/*"])
    for key in ("specs", "release_branches"):
        cfg[key] = _str_list(cfg, key, where)
    cfg.setdefault("changelog_heading", "What changed")
    if not isinstance(cfg["changelog_heading"], str) or not cfg["changelog_heading"].strip():
        raise DeliveryError("%s: 'changelog_heading' must be a non-empty string" % where)
    minutes = cfg.setdefault("timeout_minutes", DEFAULT_TIMEOUT_MINUTES)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
        raise DeliveryError("%s: 'timeout_minutes' must be an integer >= 1" % where)
    pk = cfg.get("packages")
    if not isinstance(pk, dict) or pk.get("kind") not in PACKAGE_KINDS:
        raise DeliveryError(
            "%s: packages.kind must be one of %s" % (where, ", ".join(PACKAGE_KINDS))
        )
    steps = cfg.get("steps")
    if not isinstance(steps, list) or not steps:
        raise DeliveryError("%s: 'steps' must be a non-empty list" % where)
    seen = set()
    for i, step in enumerate(steps):
        label = "%s: steps[%d]" % (where, i)
        if not isinstance(step, dict):
            raise DeliveryError("%s must be an object" % label)
        name = step.get("name")
        if not isinstance(name, str) or not name:
            raise DeliveryError("%s needs a 'name'" % label)
        if name in seen:
            raise DeliveryError("%s: duplicate step name '%s'" % (where, name))
        if name == SETUP_STEP:
            raise DeliveryError("%s: '%s' is reserved for the \"setup\" commands" % (label, name))
        seen.add(name)
        if step.get("scope") not in SCOPES:
            raise DeliveryError("%s ('%s'): scope must be one of %s" % (label, name, ", ".join(SCOPES)))
        if not isinstance(step.get("run"), str) or not step["run"].strip():
            raise DeliveryError("%s ('%s') needs a 'run' command" % (label, name))
        if "run_full" in step and not isinstance(step["run_full"], str):
            raise DeliveryError("%s ('%s'): 'run_full' must be a string" % (label, name))
        step["pre_push"] = bool(step.get("pre_push", False))
        env = step.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(k, str) and k and isinstance(v, str) for k, v in env.items()
        ):
            raise DeliveryError("%s ('%s'): 'env' must map names to string values" % (label, name))
        step["env"] = env
    return cfg


# --------------------------------------------------------------------------
# package discovery
# --------------------------------------------------------------------------

def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def parse_pnpm_patterns(text: str) -> list[str]:
    """The `packages:` list of pnpm-workspace.yaml. Handles block lists and a
    one-line flow list; ignores everything else."""
    patterns: list[str] = []
    in_list = False
    for raw in text.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if not line.strip():
            continue
        m = re.match(r"^packages\s*:\s*(.*)$", line)
        if m:
            rest = m.group(1).strip()
            if rest.startswith("["):
                inner = rest.strip("[]")
                patterns += [_unquote(p) for p in inner.split(",") if p.strip()]
                in_list = False
            else:
                in_list = True
            continue
        if in_list:
            m = re.match(r"^\s*-\s*(.+?)\s*$", line)
            if m:
                patterns.append(_unquote(m.group(1)))
            elif not line[0].isspace():
                in_list = False
    return patterns


def _expand(root: Path, include: list[str], exclude: list[str], must_contain: str | None) -> list[str]:
    found: set[str] = set()
    for pat in include:
        pat = pat.strip()
        if pat.startswith("./"):
            pat = pat[2:]
        pat = pat.rstrip("/")
        if not pat:
            continue
        prefix = pat.split("**")[0].rstrip("/") if "**" in pat else None
        for hit in glob.glob(pat, root_dir=str(root), recursive=True):
            rel = posix(hit).rstrip("/")
            if rel == prefix:  # 'packages/**' lists 'packages/' itself; it is not a package
                continue
            if (root / hit).is_dir() and not _SKIP_DIRS.intersection(rel.split("/")):
                if must_contain is None or (root / hit / must_contain).is_file():
                    found.add(rel)
    for pat in exclude:
        pat = pat.strip().rstrip("/")
        found = {f for f in found if not fnmatch.fnmatchcase(f, pat)}
    return sorted(found)


def _pnpm_packages(root: Path) -> list[str]:
    path = root / "pnpm-workspace.yaml"
    if not path.is_file():
        raise DeliveryError("packages.kind is pnpm-workspace but pnpm-workspace.yaml is missing")
    patterns = parse_pnpm_patterns(path.read_text(encoding="utf-8"))
    include = [p for p in patterns if not p.startswith("!")]
    exclude = [p[1:] for p in patterns if p.startswith("!")]
    return _expand(root, include, exclude, None)


def _cargo_packages(root: Path) -> list[str]:
    path = root / "Cargo.toml"
    if not path.is_file():
        raise DeliveryError("packages.kind is cargo-workspace but Cargo.toml is missing")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise DeliveryError("Cargo.toml is not valid TOML: %s" % exc) from None
    ws = data.get("workspace") or {}
    members = _expand(root, list(ws.get("members", [])), list(ws.get("exclude", [])), "Cargo.toml")
    if "package" in data:
        members.append(".")
    if not members:
        raise DeliveryError("Cargo.toml has no [workspace] members and no [package]")
    return sorted(set(members))


def _go_packages(root: Path) -> list[str]:
    dirs = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if "go.mod" in filenames:
            rel = posix(os.path.relpath(dirpath, root))
            dirs.append(rel)
    if not dirs:
        raise DeliveryError("packages.kind is go-modules but no go.mod was found")
    return sorted(dirs)


_SLN_PROJECT = re.compile(r'^Project\("\{[^}]+\}"\)\s*=\s*"[^"]*"\s*,\s*"([^"]+)"', re.M)
_SLNX_PROJECT = re.compile(r'<Project\s+Path="([^"]+)"')


def _dotnet_packages(root: Path) -> list[str]:
    slns = sorted(list(root.glob("*.sln")) + list(root.glob("*.slnx")))
    if not slns:
        raise DeliveryError("packages.kind is dotnet-sln but no .sln file was found in the root")
    dirs: set[str] = set()
    for sln in slns:
        text = sln.read_text(encoding="utf-8-sig", errors="replace")
        paths = _SLN_PROJECT.findall(text) + _SLNX_PROJECT.findall(text)
        for p in paths:
            p = p.replace("\\", "/")
            if not p.lower().endswith("proj"):  # solution folders have no project file
                continue
            d = posixpath.normpath(posixpath.dirname(p) or ".")
            dirs.add(d)
    if not dirs:
        raise DeliveryError("the .sln lists no projects")
    return sorted(dirs)


def discover_packages(root: Path, packages_cfg: dict) -> list[str]:
    """Package directories, POSIX, relative to the root ('.' for the root)."""
    kind = packages_cfg["kind"]
    return {
        "pnpm-workspace": _pnpm_packages,
        "cargo-workspace": _cargo_packages,
        "go-modules": _go_packages,
        "dotnet-sln": _dotnet_packages,
    }[kind](root)


# --------------------------------------------------------------------------
# change analysis
# --------------------------------------------------------------------------

def changed_files(base: str, cwd: Path) -> list[str]:
    out = run_git(["diff", "--name-only", "--no-renames", "-z", base, "HEAD"], cwd=cwd).stdout
    return sorted(f for f in out.split("\0") if f)


def package_of(path: str, packages: list[str]) -> str | None:
    """The deepest package directory holding `path`."""
    nested = [p for p in packages if p != "." and (path == p or path.startswith(p + "/"))]
    if nested:
        return max(nested, key=len)
    return "." if "." in packages else None


def changed_package_dirs(files: list[str], packages: list[str]) -> list[str]:
    return sorted({p for f in files if (p := package_of(f, packages)) is not None})


_DEP_KEYS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")


def affected_package_dirs(root: Path, packages_cfg: dict, packages: list[str], changed: list[str]) -> list[str]:
    """The changed packages plus every package that depends on one of them, directly
    or through others. Only pnpm-workspace repositories have a dependency graph we
    can read (each package.json); other kinds return the changed set. A test run
    scoped to the changed packages alone misses the tests of their dependents."""
    if packages_cfg.get("kind") != "pnpm-workspace" or not changed:
        return list(changed)
    names: dict[str, str] = {}
    deps: dict[str, set[str]] = {}
    for d in packages:
        pj = root / d / "package.json"
        if not pj.is_file():
            continue
        try:
            data = json.loads(pj.read_text(encoding="utf-8-sig"))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("name"), str):
            names[data["name"]] = d
        deps[d] = {k for key in _DEP_KEYS if isinstance(data.get(key), dict) for k in data[key]}
    dependents: dict[str, set[str]] = {}
    for d, wanted in deps.items():
        for name in wanted:
            target = names.get(name)
            if target is not None and target != d:
                dependents.setdefault(target, set()).add(d)
    seen = set(changed)
    todo = list(changed)
    while todo:
        for dep in dependents.get(todo.pop(), ()):
            if dep not in seen:
                seen.add(dep)
                todo.append(dep)
    return sorted(seen)


def widen_match(path: str, entry: str) -> bool:
    """A widen_on entry: 'dir/' (prefix), a glob containing * ? [, or a root-level
    file name. A bare name matches only at the repository root, so a package's own
    package.json does not widen the gate; use a glob such as '*packages.lock.json'
    for per-package lockfiles."""
    if any(c in entry for c in "*?["):
        return fnmatch.fnmatchcase(path, entry)
    if entry.endswith("/"):
        return path.startswith(entry)
    return path == entry or path.startswith(entry + "/")


def widening_files(files: list[str], widen_on: list[str]) -> list[str]:
    return [f for f in files if any(widen_match(f, e) for e in widen_on)]


# --------------------------------------------------------------------------
# context and step planning (shared by branch_gate.py and fast_guards.py)
# --------------------------------------------------------------------------

@dataclass
class Context:
    root: Path
    cfg: dict
    base_ref: str
    base: str
    head: str
    files: list[str]
    packages: list[str]
    changed_dirs: list[str]
    affected_dirs: list[str]
    widened: bool
    widen_reasons: list[str] = field(default_factory=list)


def build_context(root: Path, cfg: dict, base_ref: str | None, full: bool = False) -> Context:
    base_ref = base_ref or "origin/" + cfg["default_branch"]
    if rev(base_ref, root) is None:
        raise DeliveryError(
            "base ref '%s' not found. Run 'git fetch' or pass --base-ref." % base_ref
        )
    head = rev("HEAD", root)
    if head is None:
        raise DeliveryError("the repository has no commits")
    mb = run_git(["merge-base", "HEAD", base_ref], cwd=root, check=False)
    if mb.returncode != 0 or not mb.stdout.strip():
        raise DeliveryError("HEAD and '%s' have no common ancestor" % base_ref)
    base = mb.stdout.strip()
    files = changed_files(base, root)
    packages = discover_packages(root, cfg["packages"])
    reasons = widening_files(files, cfg["widen_on"])
    if full:
        reasons = ["--full"] + reasons
    changed = changed_package_dirs(files, packages)
    return Context(
        root=root,
        cfg=cfg,
        base_ref=base_ref,
        base=base,
        head=head,
        files=files,
        packages=packages,
        changed_dirs=changed,
        affected_dirs=affected_package_dirs(root, cfg["packages"], packages, changed),
        widened=bool(reasons),
        widen_reasons=reasons,
    )


def plan_step(step: dict, ctx: Context) -> tuple[bool, str | None, str]:
    """Decide one step: (run?, command with placeholders filled, reason)."""
    scope = step["scope"]
    wide = ctx.widened
    if scope == "always":
        cmd, why = step["run"], "always"
    elif scope in ("changed", "changed+dependents"):
        if wide:
            cmd, why = step.get("run_full") or step["run"], "widened"
        elif not ctx.changed_dirs:
            return False, None, "no package changed"
        else:
            cmd, why = step["run"], "package changed"
    else:  # ui-changed
        ui = [f for f in ctx.files if any(f.startswith(p) for p in ctx.cfg["ui_paths"])]
        if not wide and not ui:
            return False, None, "no ui_paths change"
        cmd = (step.get("run_full") if wide else None) or step["run"]
        why = "widened" if wide else "ui path changed"
    cmd = (
        cmd.replace("{base}", ctx.base)
        .replace("{changed_dirs}", " ".join(ctx.packages if wide else ctx.changed_dirs))
        .replace("{affected_dirs}", " ".join(ctx.packages if wide else ctx.affected_dirs))
    )
    return True, cmd, why


def run_command(cmd: str, cwd: Path, env: dict[str, str] | None = None) -> tuple[int, float]:
    """Run a command through the shell, output inherited, no log and no limit
    (join.py's lockfile re-setup). `env` is added to the environment (a step's
    "env" in gate.json: the only way to set a variable that works in cmd.exe and sh
    alike). Returns (code, seconds)."""
    sys.stdout.flush()
    sys.stderr.flush()
    start = time.monotonic()
    full_env = {**os.environ, **env} if env else None
    code = subprocess.run(cmd, shell=True, cwd=cwd, env=full_env).returncode
    return code, round(time.monotonic() - start, 1)


# --------------------------------------------------------------------------
# running steps: logs, time limits, process trees
# --------------------------------------------------------------------------

def kill_tree(proc: subprocess.Popen) -> None:
    """Kill a step and everything it started. POSIX: run_logged starts the step in
    its own session, so its process group is the whole tree. Windows: taskkill /T
    follows the parent links from the shell down."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _pump(stream, log) -> None:
    """Copy a step's combined output to its log file and to the terminal."""
    out = getattr(sys.stdout, "buffer", None)
    echo = True
    try:
        while True:
            chunk = stream.read1(65536)
            if not chunk:
                return
            log.write(chunk)
            log.flush()
            if echo:
                try:
                    if out is not None:
                        out.write(chunk)
                        out.flush()
                    else:
                        sys.stdout.write(chunk.decode("utf-8", "replace"))
                        sys.stdout.flush()
                except (OSError, ValueError):
                    echo = False  # the terminal went away; keep logging
    except (OSError, ValueError):
        return  # the pipe or the log was closed under us


def run_logged(
    cmd: str, cwd: Path, env: dict[str, str] | None, log, timeout: float | None
) -> tuple[int, float, bool]:
    """Run a step command through the shell. Its stdout and stderr are one stream,
    written to `log` (an open binary file) and echoed. stdin is closed, so a tool
    that waits for input fails instead of hanging. After `timeout` seconds the whole
    process tree is killed. Returns (exit code, seconds, timed out)."""
    sys.stdout.flush()
    sys.stderr.flush()
    start = time.monotonic()
    full_env = {**os.environ, **env} if env else None
    kw = {} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=cwd,
        env=full_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kw,
    )
    pump = threading.Thread(target=_pump, args=(proc.stdout, log), daemon=True)
    pump.start()
    timed_out = False
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_tree(proc)
        code = proc.wait()
    except BaseException:  # Ctrl-C: the step is in its own session and would outlive us
        kill_tree(proc)
        raise
    # A child that outlived the step can keep the pipe open; do not wait for it.
    pump.join(timeout=5)
    try:
        proc.stdout.close()
    except OSError:
        pass
    return code, round(time.monotonic() - start, 1), timed_out


def _log_name(step_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", step_name)


def _skipped(name: str, reason: str) -> dict:
    return {"name": name, "outcome": "skip", "seconds": 0.0, "command": None, "reason": reason}


def _minutes(seconds: float) -> str:
    return "%g" % round(seconds / 60, 3)


def execute_steps(
    steps: list[dict],
    ctx: Context,
    selected: set[str] | None = None,
    keep_going: bool = False,
    setup_cmds: list[str] | None = None,
    no_setup: bool = False,
    limit_seconds: float | None = None,
    per_step: bool = False,
    log_dir: str = LOG_DIR,
    log_root: Path | None = None,
) -> tuple[list[dict], bool]:
    """Run `setup_cmds` as the step "setup", then `steps` in order. Returns the
    result's step entries and whether the time limit stopped the run.

    Stops at the first failed step unless `keep_going`; a failed setup or an
    exhausted time limit always stops. `limit_seconds` is for the whole run, or for
    each step with `per_step` (a step over it fails and the run goes on). Each step's
    output goes to <log_dir>/<step>.log under `log_root` (default: the context's
    root; fast_guards.py checking a pushed commit in a temporary worktree keeps the
    logs in the main checkout, which outlives it). Commands run in ctx.root."""
    cwd = ctx.root
    root = log_root or ctx.root
    entries: list[dict] = []
    timed_out = False
    halt: str | None = None  # why every later step is skipped
    t0 = time.monotonic()

    def budget() -> float | None:
        if limit_seconds is None:
            return None
        return limit_seconds if per_step else limit_seconds - (time.monotonic() - t0)

    def run(name: str, commands: list[str], why: str, env: dict[str, str] | None) -> dict:
        nonlocal timed_out
        log_rel = "%s/%s.log" % (log_dir, _log_name(name))
        log_path = root / log_rel
        # Written under a name of its own and renamed when the step ends, so two
        # runs in one checkout (two pushes at once) never mix their output and
        # the tail printed after a failure is always this run's.
        part = root / ("%s.%d.part" % (log_rel, os.getpid()))
        part.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "name": name,
            "outcome": "pass",
            "seconds": 0.0,
            "command": " && ".join(commands),
            "reason": None,
            "exit_code": 0,
            "log": log_rel,
        }
        print("\n==> %s (%s)" % (name, why), flush=True)
        with open(part, "wb") as log:
            for cmd in commands:
                print("    $ %s" % cmd, flush=True)
                left = budget()
                code, secs, hit = run_logged(
                    cmd, cwd, env, log, None if left is None else max(left, 0.01)
                )
                entry["seconds"] = round(entry["seconds"] + secs, 1)
                if code == 0 and not hit:
                    continue
                entry.update(outcome="fail", exit_code=code)
                if hit:
                    entry["reason"] = "timed out after %s min" % _minutes(limit_seconds)
                    timed_out = timed_out or not per_step
                else:
                    entry["reason"] = "command failed" + (": " + cmd if len(commands) > 1 else "")
                break
        try:
            os.replace(part, log_path)
        except OSError:  # the final name is busy (Windows): keep this run's file
            entry["log"] = posix(part.relative_to(root))
        return entry

    if setup_cmds:
        if no_setup:
            entries.append(_skipped(SETUP_STEP, "--no-setup"))
        else:
            entry = run(SETUP_STEP, setup_cmds, "install from the lockfile", None)
            entries.append(entry)
            if entry["outcome"] == "fail":
                halt = "gate timed out" if timed_out else "setup failed"

    for step in steps:
        name = step["name"]
        reason = halt
        go, cmd, why = False, None, ""
        if reason is None and selected is not None and name not in selected:
            reason = "not selected"
        if reason is None:
            go, cmd, why = plan_step(step, ctx)
            if not go:
                reason = why
            elif not per_step and limit_seconds is not None and budget() <= 0:
                timed_out = True
                halt = reason = "gate timed out"
        if reason is not None:
            entries.append(_skipped(name, reason))
            continue
        entry = run(name, [cmd], why, step.get("env"))
        entries.append(entry)
        if entry["outcome"] == "fail":
            if timed_out:
                halt = "gate timed out"
            elif not keep_going:
                halt = "an earlier step failed"
    return entries, timed_out


def summary_table(entries: list[dict]) -> str:
    rows = [("step", "outcome", "seconds", "note")]
    for e in entries:
        rows.append((e["name"], e["outcome"].upper(), "%.1f" % e["seconds"], e.get("reason") or ""))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    lines = []
    for i, r in enumerate(rows):
        lines.append("  ".join(c.ljust(widths[j]) for j, c in enumerate(r)).rstrip())
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def _say(line: str) -> None:
    """print() that survives a console whose encoding cannot show the line."""
    try:
        print(line)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(line.encode(enc, "replace").decode(enc))


def log_tail(path: Path, lines: int = TAIL_LINES) -> list[str]:
    """The last `lines` lines of a step log ([] when there is none)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 256 * 1024))
            data = f.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()[-lines:]


def print_failures(entries: list[dict], root: Path) -> None:
    """After the summary: for each failed step, which one, why, where its log is,
    and the end of its output, so a failure never needs a re-run to be read."""
    for e in entries:
        if e["outcome"] != "fail":
            continue
        _say(
            "\nFAIL %s: %s (exit %s, %ss) - log: %s"
            % (e["name"], e.get("reason"), e.get("exit_code"), e["seconds"], e.get("log"))
        )
        tail = log_tail(root / e["log"]) if e.get("log") else []
        if not tail:
            _say("    (no output)")
        for line in tail:
            _say("    " + line)
    sys.stdout.flush()


def overall_pass(entries: list[dict], timed_out: bool = False) -> bool:
    """No step failed, the time limit did not stop the run, setup (when there is
    one) did not fail, and at least one step besides setup ran and passed."""
    if timed_out or any(e["outcome"] == "fail" for e in entries):
        return False
    return any(e["outcome"] == "pass" for e in entries if e["name"] != SETUP_STEP)


def is_lockfile(path: str, cfg: dict) -> bool:
    name = posixpath.basename(path)
    return name in DEFAULT_LOCKFILES or path in cfg.get("lockfiles", []) or name in cfg.get("lockfiles", [])


def main_guard(fn):
    """Run fn(); turn DeliveryError into a message and its exit code."""
    try:
        sys.exit(fn())
    except DeliveryError as exc:
        eprint("error: %s" % exc)
        sys.exit(exc.code)
    except KeyboardInterrupt:
        eprint("interrupted")
        sys.exit(130)
