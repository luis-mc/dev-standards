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
# How a lockfile change is scoped (gate.json "lockfile_scope"). "widen" (the default)
# leaves lockfiles to "widen_on". "pnpm-importers" reads pnpm-lock.yaml's importers
# section; "per-package" means each package keeps its own lockfile (go.mod/go.sum,
# packages.lock.json), which belongs to the package directory it sits in.
LOCKFILE_SCOPES = ("widen", "pnpm-importers", "per-package")
DEFAULT_INERT_PATHS = ["docs/**"]  # gate.json "inert_paths" when absent
PNPM_LOCK = "pnpm-lock.yaml"

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


def _check_e2e_map(value: object, where: str) -> dict:
    """Validate the optional "e2e_map" (CONTRACT.md, U1) and fill its defaults."""
    label = "%s: 'e2e_map'" % where
    if not isinstance(value, dict):
        raise DeliveryError("%s must be an object" % label)
    specs = value.get("specs", [])
    if not isinstance(specs, list):
        raise DeliveryError("%s: 'specs' must be a list" % label)
    clean = []
    for i, item in enumerate(specs):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("spec"), str)
            or not item["spec"].strip()
            or not isinstance(item.get("paths"), list)
            or not item["paths"]
            or not all(isinstance(p, str) and p for p in item["paths"])
        ):
            raise DeliveryError(
                "%s: specs[%d] needs a 'spec' file and a non-empty list of 'paths'" % (label, i)
            )
        clean.append({"spec": item["spec"].strip(), "paths": list(item["paths"])})
    return {"specs": clean, "full_on": _str_list(value, "full_on", label)}


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
    if "inert_paths" in cfg:
        cfg["inert_paths"] = _str_list(cfg, "inert_paths", where)
    else:
        cfg["inert_paths"] = list(DEFAULT_INERT_PATHS)
    scope = cfg.setdefault("lockfile_scope", "widen")
    if scope not in LOCKFILE_SCOPES:
        raise DeliveryError("%s: 'lockfile_scope' must be one of %s" % (where, ", ".join(LOCKFILE_SCOPES)))
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
    if "e2e_map" in cfg:
        cfg["e2e_map"] = _check_e2e_map(cfg["e2e_map"], where)
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


def inert_only(old: str, new: str, inert_paths: list[str], cwd: Path | str | None = None) -> tuple[bool, int, list[str]]:
    """(ok, commits, offending files): `old` is an ancestor of `new` and the
    difference between them touches only inert paths (gate.json "inert_paths").
    The net difference decides, so a merge commit counts by its diff and a change
    made and reverted inside the range counts as nothing. `commits` is the number
    of commits in old..new."""
    if not inert_paths or not is_ancestor(old, new, cwd):
        return False, 0, []
    out = run_git(["diff", "--name-only", "--no-renames", "-z", old, new], cwd=cwd, check=False)
    if out.returncode != 0:
        return False, 0, []
    files = sorted(f for f in out.stdout.split("\0") if f)
    bad = [f for f in files if not any(widen_match(f, e) for e in inert_paths)]
    n = run_git(["rev-list", "--count", "%s..%s" % (old, new)], cwd=cwd, check=False)
    count = int(n.stdout.strip()) if n.returncode == 0 and n.stdout.strip().isdigit() else 0
    return not bad, count, bad


def _git_show(cwd: Path, rev_: str, path: str) -> str | None:
    p = run_git(["show", "%s:%s" % (rev_, path)], cwd=cwd, check=False)
    return p.stdout.replace("\r\n", "\n") if p.returncode == 0 else None


def split_pnpm_lock(text: str) -> tuple[dict[str, str], str]:
    """(importers, rest) of a pnpm-lock.yaml: each importer's block of text keyed by
    its path, and everything outside the `importers:` section. Text only, no YAML
    parser; a block that changed in any way differs."""
    importers: dict[str, list[str]] = {}
    rest: list[str] = []
    in_imp = False
    cur: str | None = None
    for line in text.split("\n"):
        if re.match(r"^\S", line):  # a top-level key
            in_imp = line.startswith("importers:")
            cur = None
            if not in_imp:
                rest.append(line)
            continue
        if not in_imp:
            rest.append(line)
            continue
        m = re.match(r"^  (\S.*?):\s*$", line)
        if m:
            cur = _unquote(m.group(1))
            importers[cur] = []
        elif cur is not None and line.strip():
            importers[cur].append(line)
    return {k: "\n".join(v) for k, v in importers.items()}, "\n".join(r for r in rest if r.strip())


def lockfile_effect(root: Path, cfg: dict, base: str, files: list[str], packages: list[str]) -> tuple[list[str], list[str]]:
    """(packages whose dependencies a lockfile change touches, reasons to widen).
    Only for a gate.json with "lockfile_scope" "pnpm-importers" and a pnpm-lock.yaml
    in `files` (CONTRACT.md, DL4). The importers whose block differs between the
    base and HEAD are the packages whose dependencies changed: they count as
    changed, so their steps run scoped. The gate widens when the change cannot be
    attributed to a package: the root importer, a change outside the importers
    section, a lockfile missing on one side."""
    if cfg.get("lockfile_scope") != "pnpm-importers" or PNPM_LOCK not in files:
        return [], []
    # An old gate.json that still lists the lockfile in widen_on widens through
    # widening_files already; the result here only adds to it.
    old, new = _git_show(root, base, PNPM_LOCK), _git_show(root, "HEAD", PNPM_LOCK)
    if old is None or new is None:
        return [], [PNPM_LOCK + " (added or removed)"]
    a, rest_a = split_pnpm_lock(old)
    b, rest_b = split_pnpm_lock(new)
    changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    if "." in changed:
        return [], [PNPM_LOCK + " (the root importer's dependencies changed)"]
    if not changed and rest_a != rest_b:
        return [], [PNPM_LOCK + " (resolutions changed outside any importer)"]
    return [c for c in changed if c in packages], []


# --------------------------------------------------------------------------
# context and step planning (shared by branch_gate.py and fast_guards.py)
# --------------------------------------------------------------------------

def split_remote_ref(ref: str, cwd: Path | str | None = None) -> tuple[str, str] | None:
    """('origin', 'x') for 'origin/x' when 'origin' is a remote of this repository;
    None for a local branch or a commit."""
    head, sep, tail = ref.partition("/")
    if sep and tail and head in remotes(cwd):
        return head, tail
    return None


def fetch_base(root: Path, base_ref: str) -> tuple[bool, str | None]:
    """Fetch the base branch before the merge base is taken (CONTRACT.md, U2):
    `git fetch --quiet --no-tags <remote> <branch>`. Returns (fetched, reason it
    was not). A ref that is not <remote>/<branch> has nothing to fetch (reason
    None). Never prompts for credentials."""
    parts = split_remote_ref(base_ref, root)
    if parts is None:
        return False, None
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        p = run_git(["fetch", "--quiet", "--no-tags", parts[0], parts[1]], cwd=root, check=False, env=env)
    except DeliveryError as exc:
        return False, str(exc)
    if p.returncode == 0:
        return True, None
    lines = [ln.strip() for ln in (p.stderr or p.stdout).splitlines() if ln.strip()]
    return False, lines[0] if lines else "fetch exited %d" % p.returncode


def fork_point_base(root: Path, commit: str, default_branch: str, pushed_branch: str = "") -> str:
    """The remote branch `commit` was most likely cut from (CONTRACT.md, U3): among
    refs/remotes/<remote>/* (not HEAD, not the pushed branch itself) the one whose
    merge base with `commit` is nearest to it, i.e. the fewest commits in
    <merge-base>..<commit>. Ties go to the default branch, then to name order. No
    candidate: the default branch."""
    names = remotes(root)
    remote = "origin" if "origin" in names else (names[0] if names else "origin")
    prefix = "refs/remotes/%s/" % remote
    out = git(["for-each-ref", "--format=%(refname)", prefix], cwd=root, check=False)
    fallback = "%s/%s" % (remote, default_branch)
    best: tuple[int, int, str] | None = None
    for ref in out.splitlines():
        name = ref[len(prefix):]
        if not name or name == "HEAD" or name == pushed_branch:
            continue
        mb = run_git(["merge-base", commit, ref], cwd=root, check=False)
        if mb.returncode != 0 or not mb.stdout.strip():
            continue
        n = run_git(["rev-list", "--count", "%s..%s" % (mb.stdout.strip(), commit)], cwd=root, check=False)
        if n.returncode != 0:
            continue
        key = (int(n.stdout.strip() or 0), 0 if name == default_branch else 1, name)
        if best is None or key < best:
            best = key
    return fallback if best is None else "%s/%s" % (remote, best[2])


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
    base_fetched: bool = False
    lock_dirs: list[str] = field(default_factory=list)  # packages a lockfile change touches


def build_context(root: Path, cfg: dict, base_ref: str | None, full: bool = False) -> Context:
    base_ref = base_ref or "origin/" + cfg["default_branch"]
    fetched, why_not = fetch_base(root, base_ref)
    if why_not:
        eprint("warning: base not fetched: %s; using the local ref" % why_not)
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
    lock_dirs, lock_reasons = lockfile_effect(root, cfg, base, files, packages)
    reasons += lock_reasons
    if full:
        reasons = ["--full"] + reasons
    changed = sorted(set(changed_package_dirs(files, packages)) | set(lock_dirs))
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
        base_fetched=fetched,
        lock_dirs=lock_dirs,
    )


def is_ui_dir(path: str, ui_paths: list[str]) -> bool:
    return any((path + "/").startswith(p if p.endswith("/") else p + "/") for p in ui_paths)


def e2e_spec_dir(root: Path, package: str) -> str | None:
    """Where a ui package keeps its end-to-end specs when there is no e2e_map:
    `<package>/e2e` or `e2e/<last segment of the package path>` (CONTRACT.md, DL4)."""
    for cand in (package + "/e2e", "e2e/" + package.rsplit("/", 1)[-1]):
        if (root / cand).is_dir():
            return cand
    return None


def e2e_derived(ctx: Context) -> list[str]:
    """The spec directories to run without an e2e_map (CONTRACT.md, DL4): those of
    the ui packages the change affects (a changed package and every ui package that
    depends on it, from the workspace graph). Empty when the specs cannot be
    determined, which means the whole suite: not a pnpm workspace, a changed ui
    file outside any package, or a changed ui package that neither has specs nor is
    imported by a ui package that has."""
    ui_paths = ctx.cfg["ui_paths"]
    if ctx.cfg["packages"]["kind"] != "pnpm-workspace" or not ui_paths:
        return []
    changed_ui: set[str] = set()
    for f in ctx.files:
        if is_ui_dir(f, ui_paths):
            pkg = package_of(f, ctx.packages)
            if pkg is None or not is_ui_dir(pkg, ui_paths):
                return []
            changed_ui.add(pkg)
    changed_ui |= {d for d in ctx.lock_dirs if is_ui_dir(d, ui_paths)}
    if not changed_ui:
        return []
    own = {d: e2e_spec_dir(ctx.root, d) for d in ctx.affected_dirs if is_ui_dir(d, ui_paths)}
    for pkg in changed_ui:
        users = affected_package_dirs(ctx.root, ctx.cfg["packages"], ctx.packages, [pkg])
        if not any(own.get(d) for d in users):
            return []  # nothing that imports this package has specs, and it has none itself
    return sorted({s for s in own.values() if s})


def e2e_selection(ctx: Context) -> tuple[str, list[str]]:
    """('affected', specs) when gate.json's "e2e_map" covers every changed UI file
    and no changed file is in "full_on"; otherwise ('full', []) (CONTRACT.md, U1).
    A widened gate is always 'full'. Without a map the specs come from the
    workspace dependency graph (e2e_derived)."""
    emap = ctx.cfg.get("e2e_map")
    if not emap or ctx.widened:
        specs = e2e_derived(ctx) if not emap and not ctx.widened else []
        return ("affected", specs) if specs else ("full", [])
    if any(widen_match(f, e) for f in ctx.files for e in emap["full_on"]):
        return "full", []
    specs: set[str] = set()
    for f in ctx.files:
        hits = [m["spec"] for m in emap["specs"] if any(widen_match(f, p) for p in m["paths"])]
        if not hits and any(f.startswith(p) for p in ctx.cfg["ui_paths"]):
            return "full", []  # a UI file no spec claims
        specs.update(hits)
    return ("affected", sorted(specs)) if specs else ("full", [])


def e2e_info(step: dict, ctx: Context) -> dict:
    """The result fields of a step that takes {e2e_specs}: selection and specs."""
    if step["scope"] != "ui-changed" or "{e2e_specs}" not in step["run"]:
        return {}
    selection, specs = e2e_selection(ctx)
    return {"selection": selection, "specs": specs}


def plan_step(step: dict, ctx: Context) -> tuple[bool, str | None, str]:
    """Decide one step: (run?, command with placeholders filled, reason)."""
    scope = step["scope"]
    wide = ctx.widened
    e2e_specs = ""
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
        ui += [d for d in ctx.lock_dirs if is_ui_dir(d, ctx.cfg["ui_paths"])]
        if not wide and not ui:
            return False, None, "no ui_paths change"
        cmd = (step.get("run_full") if wide else None) or step["run"]
        why = "widened" if wide else "ui path changed"
        if ctx.cfg.get("e2e_map") and not wide:
            selection, specs = e2e_selection(ctx)
            if selection == "affected":
                cmd, why, e2e_specs = step["run"], "affected specs", " ".join(specs)
            else:
                cmd, why = step.get("run_full") or step["run"], "full suite (e2e_map)"
        elif not wide and "{e2e_specs}" in step["run"]:
            selection, specs = e2e_selection(ctx)  # no map: from the dependency graph
            if selection == "affected":
                cmd, why, e2e_specs = step["run"], "affected specs (dependency graph)", " ".join(specs)
    cmd = (
        cmd.replace("{e2e_specs}", e2e_specs)
        .replace("{base}", ctx.base)
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
        entry.update(e2e_info(step, ctx))
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


def ledger_record(root, op: str, **kw) -> bool:
    """Best effort: write to the delivery ledger (.delivery/ledger.json) through the
    luismc-delivery plugin's delivery_ledger module. A no-op, returning False, when the
    module or the .delivery/ folder is absent or anything fails; it never raises.
    The module is found on sys.path, in $DELIVERY_PLUGIN_DIR/scripts, or in an installed
    plugin folder under ~/.claude/plugins."""
    try:
        if root is None or not (Path(root) / ".delivery").is_dir():
            return False
        mod = sys.modules.get("delivery_ledger")
        if mod is None:
            dirs = []
            env = os.environ.get("DELIVERY_PLUGIN_DIR")
            if env:
                dirs.append(Path(env) / "scripts")
            home = Path.home() / ".claude" / "plugins"
            if home.is_dir():
                dirs += [p.parent for p in home.glob("**/delivery/scripts/delivery_ledger.py")][:3]
            for d in dirs:
                if (d / "delivery_ledger.py").is_file():
                    sys.path.insert(0, str(d))
                    try:
                        import delivery_ledger as mod  # noqa: F811
                    finally:
                        sys.path.remove(str(d))
                    break
            else:
                import delivery_ledger as mod  # noqa: F811
        return bool(mod.record(root, op, by=kw.pop("by", "delivery-script"), **kw))
    except Exception:  # noqa: BLE001 - recording never breaks a delivery script
        return False


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
