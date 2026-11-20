#!/usr/bin/env python3
"""Narrow the rerun of a test job after a red run (DL375, decision D312, proposal D106).

    rerun_tests.py --runner R --prev-conclusion C [--job ID] [--report FILE] [--log FILE]
                   [--changed-file FILE|-] [--scope-config FILE] [--areas FILE] [--test-files FILE|-]
                   [--job-config FILE] [--json]

Runners: pytest (also unittest), vitest (also jest), playwright, go, cargo, nextest.

After a red run, the next head's run of a test job runs the tests that failed on that run plus the tests of the
code changed since that run's head. It runs the whole job when:
  - `ci.jobs.<job-id>.rerun` is "whole" (default "failed+changed"; read from .delivery/config.json);
  - the previous run was cancelled, timed out or ended in any state other than failure;
  - a valve changed: a lockfile, a toolchain file, a workflow file, a CI script under scripts/delivery or
    scripts/ci, or a file ci_scope.py counts as full or CI-only (`full_files`, `ci_files`);
  - the failure list cannot be read (no report and no log, an unknown format, a failed run with no failed test);
  - a changed code file maps to no test (area_select.py: no area, or an area without `tests`), or the runner
    (cargo, nextest) cannot select tests by file.
After a green previous run (or none) the answer is `current`: the job runs as it does today.

The failure list comes from the previous run's test report when there is one (JUnit XML, Playwright JSON, `go test
-json`), otherwise from the job log (pytest and unittest summary lines, vitest and jest FAIL lines, go test, cargo
libtest `test X ... FAILED` lines and the `failures:` block, nextest `FAIL [..] id name` lines).

Output: {"mode": "narrow"|"whole"|"current", "reason", "invocations": [[runner args], ...], "failed": N,
"changed_tests": [...]}. One invocation per package (go) or test binary (cargo); the others have one or a few. The
arguments are what follows the runner command: pytest node ids, vitest `FILE -t REGEX`, Playwright `FILE:LINE` (or
`FILE --grep REGEX`), go `PKG -run REGEX`, cargo `[-p CRATE] --lib|--test T|--bin B|--doc -- --exact NAMES`, nextest
`-E FILTERSET`.

A narrowed green run is not the merge gate. The ready PR's full CI is.
Exit 0 always except bad usage (2). Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from area_select import any_match, select  # noqa: E402
from ci_scope import decide as scope_decide, norm  # noqa: E402

RUNNERS = ("pytest", "vitest", "playwright", "go", "cargo", "nextest")
RERUN_DEFAULT = "failed+changed"
VALVES = [
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock",
    "uv.lock", "poetry.lock", "Pipfile.lock", "Cargo.lock", "go.sum", "go.mod", "composer.lock", "Gemfile.lock",
    "**/package-lock.json", "**/pnpm-lock.yaml", "**/yarn.lock", "**/uv.lock", "**/poetry.lock",
    "**/Cargo.lock", "**/go.sum", "**/go.mod",
    "rust-toolchain", "rust-toolchain.toml", ".nvmrc", ".node-version", ".python-version", ".tool-versions",
    ".github/workflows", "scripts/delivery", "scripts/ci",
]
TEST_FILES = {  # which repo files are tests for a runner
    "pytest": ["**/test_*.py", "**/*_test.py", "test_*.py", "*_test.py"],
    "vitest": ["**/*.test.*", "**/*.spec.*", "*.test.*"],
    "playwright": ["**/*.spec.*", "*.spec.*"],
    "go": ["**/*_test.go", "*_test.go"],
}


class Unreadable(Exception):
    """The failure list cannot be read, so the whole job runs."""


def _f(name, file="", package="", binary="", line=0):
    return {"name": name, "file": file, "package": package, "binary": binary, "line": line}


# ---------------------------------------------------------------- parsers

def _junit(text, runner):
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise Unreadable(f"bad JUnit XML: {exc}") from exc
    out = []
    for case in root.iter("testcase"):
        if not any(c.tag in ("failure", "error") for c in case):
            continue
        cls, name, file = case.get("classname") or "", case.get("name") or "", case.get("file") or ""
        if runner == "pytest":
            if not file:
                parts = cls.split(".")
                i = next((k for k, p in enumerate(parts) if p[:1].isupper()), len(parts))
                file = "/".join(parts[:i]) + ".py" if parts[:i] else ""
                cls = "::".join(parts[i:])
            else:
                mod = file[:-3].replace("/", ".")
                cls = cls[len(mod) + 1:].replace(".", "::") if cls.startswith(mod + ".") else ""
            node = "::".join(x for x in (file, cls, name) if x)
            if not file:
                raise Unreadable(f"no file for failed test {name}")
            out.append(_f(node, file))
        else:  # vitest / jest: classname is the file, name is "suite > test"
            out.append(_f(re.sub(r"\s*>\s*", " ", name), file or cls))
    return out


def _pytest_log(text):
    out = []
    for m in re.finditer(r"^(?:FAILED|ERROR) (\S+?\.py)(::\S+?)?(?: - .*)?$", text, re.M):
        if m.group(2):
            out.append(_f(m.group(1) + m.group(2), m.group(1)))
    for m in re.finditer(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)$", text, re.M):  # unittest
        parts = m.group(2).split(".")
        out.append(_f("::".join(["/".join(parts[:-2]) + ".py", parts[-2], m.group(1)]), "/".join(parts[:-2]) + ".py"))
    return out


def _vitest_log(text):
    out, cur = [], ""
    for line in text.splitlines():
        m = re.match(r"^\s*(?:FAIL|×|✗)\s+(\S+\.[cm]?[jt]sx?)\s*(?:>\s*(.+?))?(?:\s+\d+ms)?$", line)
        if m and m.group(2):
            out.append(_f(re.sub(r"\s*>\s*", " ", m.group(2).strip()), m.group(1)))
            continue
        m = re.match(r"^\s*FAIL\s+(\S+\.[cm]?[jt]sx?)\s*$", line)  # jest
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"^\s*● (.+?)$", line)
        if m and cur and "›" in m.group(1):
            out.append(_f(re.sub(r"\s*›\s*", " ", m.group(1).strip()), cur))
    return out


def _playwright(text):
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Unreadable(f"bad Playwright JSON: {exc}") from exc
    if not isinstance(data, dict) or "suites" not in data:
        raise Unreadable("not a Playwright JSON report")
    out = []

    def walk(suite):
        for spec in suite.get("specs", []):
            bad = spec.get("ok") is False or any(t.get("status") == "unexpected" for t in spec.get("tests", []))
            if bad:
                out.append(_f(spec.get("title", ""), spec.get("file") or suite.get("file") or "", line=int(spec.get("line") or 0)))
        for sub in suite.get("suites", []):
            sub.setdefault("file", suite.get("file", ""))
            walk(sub)

    for s in data["suites"]:
        walk(s)
    return out


def _go(text):
    out, pending, seen_pkg_fail = [], [], False
    if text.lstrip().startswith("{"):
        for line in text.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("Action") == "fail" and ev.get("Test") and "/" not in ev["Test"]:
                out.append(_f(ev["Test"], package=ev.get("Package", "")))
            elif ev.get("Action") == "fail" and not ev.get("Test"):
                seen_pkg_fail = True
        if seen_pkg_fail and not out:
            raise Unreadable("a package failed with no failed test")
        return out
    for line in text.splitlines():
        m = re.match(r"^\s*--- FAIL: ([^\s/]+)(?:/\S+)?\s", line + " ")
        if m:
            if m.group(1) not in pending:
                pending.append(m.group(1))
            continue
        m = re.match(r"^FAIL[\t ]+(\S+)(?:[\t ]+(.*))?$", line)
        if m:
            if "[build failed]" in (m.group(2) or "") or "[setup failed]" in (m.group(2) or ""):
                raise Unreadable("go package did not build")
            if not pending:
                raise Unreadable(f"package {m.group(1)} failed with no failed test")
            out += [_f(n, package=m.group(1)) for n in pending]
            pending = []
    if pending:
        raise Unreadable("failed tests with no package line")
    return out


def _cargo(text):
    out, binary, names = [], None, []

    def target(src, dep):
        crate = re.sub(r"-[0-9a-f]{8,}$", "", dep.rsplit("/", 1)[-1]).replace("_", "-")
        head = re.split(r"(?:^|/)(?:src|tests)/", src, maxsplit=1)[0].rstrip("/")
        pkg = head.rsplit("/", 1)[-1] if head else ""
        if src.startswith("tests/") or "/tests/" in src:
            return (pkg, ["--test", Path(src).stem])
        if src.endswith("lib.rs"):
            return (pkg, ["--lib"])
        return (pkg, ["--bin", crate])

    for line in text.splitlines():
        m = re.match(r"^\s*Running (?:unittests )?(\S+) \(([^)]+)\)", line)
        if m:
            binary = target(m.group(1), m.group(2))
            continue
        if re.match(r"^\s*Doc-tests ", line):
            binary = ("", ["--doc"])
            continue
        m = re.match(r"^test (\S+) \.\.\. FAILED\s*$", line)
        if m:
            out.append(_f(m.group(1), binary=json.dumps(binary)))
    if not out and re.search(r"^failures:\s*$", text, re.M):
        block = text.rsplit("failures:", 1)[1]
        for line in block.splitlines():
            if re.match(r"^    \S+$", line):
                names.append(line.strip())
            elif names and not line.strip():
                break
        out = [_f(n, binary=json.dumps(binary)) for n in names]
    if binary is None and out:
        raise Unreadable("failed cargo tests with no binary line")
    return out


def _nextest(text):
    out, seen = [], set()
    for m in re.finditer(r"^\s*(?:FAIL|TIMEOUT|SIG[A-Z]+|LEAK-FAIL)\s+\[[^\]]*\]\s+(\S+)\s+(\S+)\s*$", text, re.M):
        key = (m.group(1), m.group(2))
        if key not in seen:
            seen.add(key)
            out.append(_f(m.group(2), binary=m.group(1)))
    return out


def parse_failures(runner, text):
    """The failed tests in `text` (a report or a log) for `runner`. Raises Unreadable."""
    if runner not in RUNNERS:
        raise Unreadable(f"unknown runner {runner!r}")
    if not isinstance(text, str) or not text.strip():
        raise Unreadable("empty report")
    body = text.lstrip()
    if runner in ("pytest", "vitest") and body.startswith("<"):
        found = _junit(text, runner)
    elif runner == "pytest":
        found = _pytest_log(text)
    elif runner == "vitest":
        found = _vitest_log(text)
    elif runner == "playwright":
        found = _playwright(text)
    elif runner == "go":
        found = _go(text)
    elif runner == "cargo":
        found = _cargo(text)
    else:
        found = _nextest(text)
    if not found:
        raise Unreadable("no failed test found in the report")
    return found


def read_failures(runner, report=None, log=None):
    """Report first, then the job log. Raises Unreadable when neither gives a list."""
    errors = []
    for label, text in (("report", report), ("log", log)):
        if text:
            try:
                return parse_failures(runner, text)
            except Unreadable as exc:
                errors.append(f"{label}: {exc}")
    raise Unreadable("; ".join(errors) or "no report and no log")


# ---------------------------------------------------------------- arguments

def _rx(names):
    return "^(?:" + "|".join(re.escape(n) for n in names) + ")$"


def build_invocations(runner, failed, extra_files=()):
    """Runner arguments, as a list of invocations. `extra_files`: test files of changed code, run whole."""
    extra = list(dict.fromkeys(extra_files))
    inv = []
    if runner == "pytest":
        ids = [f["name"] for f in failed if f["file"] not in extra]
        inv.append(list(dict.fromkeys(ids + extra)))
    elif runner == "vitest":
        by = {}
        for f in failed:
            if f["file"] not in extra:
                by.setdefault(f["file"], []).append(f["name"])
        inv += [[fl, "-t", _rx(ns)] for fl, ns in by.items()]
        if extra:
            inv.append(extra)
    elif runner == "playwright":
        spots = [f"{f['file']}:{f['line']}" for f in failed if f["line"] and f["file"] not in extra]
        by = {}
        for f in failed:
            if not f["line"] and f["file"] not in extra:
                by.setdefault(f["file"], []).append(f["name"])
        if spots or extra:
            inv.append(list(dict.fromkeys(spots)) + extra)
        inv += [[fl, "--grep", _rx(ns)] for fl, ns in by.items()]
    elif runner == "go":
        by = {}
        for f in failed:
            by.setdefault(f["package"], []).append(f["name"])
        for pkg, names in by.items():
            inv.append([pkg, "-run", "^(" + "|".join(dict.fromkeys(names)) + ")$"])
        inv += [[p] for p in extra if not any(k == p.lstrip("./") or k.endswith("/" + p.lstrip("./")) for k in by)]
    elif runner == "cargo":
        by = {}
        for f in failed:
            by.setdefault(f["binary"], []).append(f["name"])
        for key, names in by.items():
            pkg, sel = json.loads(key)
            inv.append((["-p", pkg] if pkg else []) + sel + ["--", "--exact"] + list(dict.fromkeys(names)))
    else:  # nextest
        terms = []
        for f in failed:
            if not re.fullmatch(r"[\w:<>\[\]]+", f["name"]):
                raise Unreadable(f"test name {f['name']!r} cannot go in a filterset")
            terms.append(f"(binary_id(={f['binary']}) & test(={f['name']}))")
        inv.append(["-E", " | ".join(dict.fromkeys(terms))])
    return [i for i in inv if i]


# ---------------------------------------------------------------- decision

def _valve(changed, scope_cfg):
    for f in changed:
        if any_match(f, VALVES):
            return f
    if not changed:
        return None
    res = scope_decide(scope_cfg or {}, changed)
    if res["scope"] != "affected":
        return f"{res['scope']} scope: {res['why']}"
    return None


def changed_tests(runner, changed, areas, test_files):
    """Test files of the changed code, or None when a changed file maps to no test (then run whole)."""
    cfg = areas or {}
    docs = cfg.get("docs") or []
    code = [f for f in changed if not any_match(f, docs)]
    if not code:
        return []
    if runner in ("cargo", "nextest") or test_files is None or not cfg:
        return None
    sel = select(code, cfg)
    if sel["mode"] == "all":
        return None
    globs = sel.get("tests") or []
    if sel["mode"] == "areas" and not globs:
        return None
    kinds = TEST_FILES[runner]
    own = [f for f in code if any_match(f, kinds)]
    mapped = [t for t in test_files if any_match(t, globs) and any_match(t, kinds)]
    out = list(dict.fromkeys(own + mapped))
    if runner == "go":
        out = list(dict.fromkeys("./" + (t.rsplit("/", 1)[0] if "/" in t else ".") for t in out))
    return out


def decide(runner, job_id="", prev=None, changed=(), scope_cfg=None, areas=None, test_files=None, job_cfg=None):
    """prev: {"conclusion": str, "report": str|None, "log": str|None} of the previous run's job, or None."""
    def out(mode, reason, inv=(), failed=0, tests=()):
        return {"mode": mode, "reason": reason, "invocations": [list(i) for i in inv], "failed": failed,
                "changed_tests": list(tests)}
    mode_cfg = (job_cfg or {}).get(job_id, {}).get("rerun", RERUN_DEFAULT) if isinstance(job_cfg, dict) else RERUN_DEFAULT
    if mode_cfg == "whole":
        return out("whole", f"ci.jobs.{job_id}.rerun is whole")
    if not prev:
        return out("current", "no previous run: today's behaviour")
    concl = prev.get("conclusion")
    if concl == "success":
        return out("current", "the previous run was green: today's behaviour")
    if concl != "failure":
        return out("whole", f"the previous run ended {concl or 'unknown'}, not failure")
    files = [norm(f) for f in changed if f and f.strip()]
    hit = _valve(files, scope_cfg)
    if hit:
        return out("whole", f"valve changed: {hit}")
    try:
        failed = read_failures(runner, prev.get("report"), prev.get("log"))
        extra = changed_tests(runner, files, areas, test_files)
        if extra is None:
            return out("whole", "changed code maps to no test file for this runner")
        inv = build_invocations(runner, failed, extra)
    except Unreadable as exc:
        return out("whole", f"failure list unreadable: {exc}")
    return out("narrow", f"{len(failed)} failed test(s) plus {len(extra)} test file(s) of changed code", inv, len(failed), extra)


# ---------------------------------------------------------------- CLI

def _read(path):
    if not path:
        return None
    try:
        return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _json_file(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8")) if path else None
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runner", required=True, choices=RUNNERS)
    ap.add_argument("--job", default="")
    ap.add_argument("--prev-conclusion", default="")
    ap.add_argument("--report")
    ap.add_argument("--log")
    ap.add_argument("--changed-file")
    ap.add_argument("--scope-config", default="scripts/delivery/ci-scope.json")
    ap.add_argument("--areas", default="scripts/delivery/ci-areas.json")
    ap.add_argument("--test-files", help="file listing the repo's files; default git ls-files")
    ap.add_argument("--job-config", default=".delivery/config.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    files = _read(a.test_files)
    if files is None:
        r = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
        files = r.stdout if r.returncode == 0 else None
    cfg = _json_file(a.job_config) or {}
    jobs = ((cfg.get("ci") or {}).get("jobs") or {}) if isinstance(cfg.get("ci"), dict) else {}
    prev = {"conclusion": a.prev_conclusion or None, "report": _read(a.report), "log": _read(a.log)} if a.prev_conclusion else None
    res = decide(a.runner, a.job, prev, (_read(a.changed_file) or "").splitlines(), _json_file(a.scope_config),
                 _json_file(a.areas), files.splitlines() if files is not None else None, jobs)
    print(json.dumps(res) if a.json else f"mode={res['mode']}\nreason={res['reason']}\n"
          + "\n".join("args=" + json.dumps(i) for i in res["invocations"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
