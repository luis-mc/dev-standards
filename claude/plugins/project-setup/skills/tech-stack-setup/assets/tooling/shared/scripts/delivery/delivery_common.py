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
import subprocess
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = 1
TOOL_VERSION = 1

EXIT_OK = 0
EXIT_FAIL = 1  # checks failed, or a result is not trusted
EXIT_USAGE = 2  # usage or configuration error; could not decide
EXIT_CONFLICT = 3  # join stopped at a conflict
EXIT_TIMEOUT = 4

SCOPES = ("always", "changed", "changed+dependents", "ui-changed")
PACKAGE_KINDS = ("pnpm-workspace", "go-modules", "cargo-workspace", "dotnet-sln")

DELIVERY_DIR = ".delivery"
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
    """Run a step command through the shell, output inherited. `env` is added to the
    environment (a step's "env" in gate.json: the only way to set a variable that
    works in cmd.exe and sh alike). Returns (code, seconds)."""
    sys.stdout.flush()
    sys.stderr.flush()
    start = time.monotonic()
    full_env = {**os.environ, **env} if env else None
    code = subprocess.run(cmd, shell=True, cwd=cwd, env=full_env).returncode
    return code, round(time.monotonic() - start, 1)


def execute_steps(
    steps: list[dict],
    ctx: Context,
    selected: set[str] | None = None,
    fail_fast: bool = False,
) -> list[dict]:
    """Run `steps` in order and return the result's step entries."""
    entries: list[dict] = []
    stopped = False
    for step in steps:
        name = step["name"]
        entry = {"name": name, "outcome": "skip", "seconds": 0.0, "command": None}
        if stopped:
            entry["reason"] = "fail-fast: an earlier step failed"
        elif selected is not None and name not in selected:
            entry["reason"] = "not selected"
        else:
            go, cmd, why = plan_step(step, ctx)
            entry["reason"] = why
            if go:
                print("\n==> %s (%s)\n    $ %s" % (name, why, cmd), flush=True)
                code, secs = run_command(cmd, ctx.root, step.get("env"))
                entry.update(
                    outcome="pass" if code == 0 else "fail", seconds=secs, command=cmd
                )
                if code != 0:
                    entry["exit_code"] = code
                    stopped = fail_fast
        entries.append(entry)
    return entries


def summary_table(entries: list[dict]) -> str:
    rows = [("step", "outcome", "seconds", "note")]
    for e in entries:
        rows.append((e["name"], e["outcome"].upper(), "%.1f" % e["seconds"], e.get("reason", "")))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    lines = []
    for i, r in enumerate(rows):
        lines.append("  ".join(c.ljust(widths[j]) for j, c in enumerate(r)).rstrip())
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def overall_pass(entries: list[dict]) -> bool:
    """No step failed and at least one ran."""
    outcomes = [e["outcome"] for e in entries]
    return "fail" not in outcomes and "pass" in outcomes


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
