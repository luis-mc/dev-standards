#!/usr/bin/env python3
"""The test guardrails guard, DL-99 (DELIVERYSPEC 1b; owner decisions D312, D313).

    test_guardrails.py [--root DIR] [--json] [--mode warn|block]

Reads the repository (never runs a test) and reports seven guardrails:

  G1  every test runner has a per-test timeout within the limits (unit 10 s, integration 60 s, e2e 120 s)
  G2  every workflow job sets timeout-minutes of 30 or less
  G3  no retries in CI
  G4  no sleeps or open-ended waits in test files
  G5  at most 20 cases per test
  G6  no mutation run or many-run property test in a pull_request or non-default push workflow
  G7  some workflow uploads test times

Config (.delivery/config.json, a missing file means the defaults):
  ci.test_guardrails.mode     "warn" (default: print, exit 0) or "block" (exit 1 on any break not turned off)
  ci.test_guardrails.off      guardrails this project turns off; each needs ci.test_guardrails.reasons.<id>,
                              else the guard reports it and keeps scanning that guardrail
  ci.jobs.<id>.timeout_minutes   G2: may only lower the 30 minute limit
  ci.jobs.<id>.test_timeout_s    G1: {unit, integration, e2e}; may only lower the limits, a higher value is a break

Exit: 0 (warn, or block with no break), 1 (block with a break), 2 usage or configuration error.
Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

GUARDRAILS = {
    "G1": "per-test timeout",
    "G2": "job timeout-minutes",
    "G3": "no retries in CI",
    "G4": "no sleeps in tests",
    "G5": "at most 20 cases per test",
    "G6": "no mutation or many-run property tests on pull requests",
    "G7": "test times reported",
}
TEST_LIMITS_S = {"unit": 10, "integration": 60, "e2e": 120}
JOB_LIMIT_MIN = 30
MAX_CASES = 20
SHOWN = 10
MAX_BYTES = 512 * 1024
SKIP_DIRS = {".git", ".delivery", "node_modules", "target", "dist", "build", ".venv", "venv", "__pycache__",
             ".next", "coverage", "vendor", ".tox", ".mypy_cache", ".pytest_cache"}
CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs"}
CMD_EXT = {".yml", ".yaml", ".json", ".sh", ".toml", ".ini", ".cfg", ".txt", ".mk"}
DEFAULT_BRANCHES = ("main", "master")


class Repo:
    """One walk of the tree; file text is read once and cached."""

    def __init__(self, root: Path):
        self.root = root
        self.files: list[str] = []
        self._text: dict[str, str] = {}
        for dirpath, dirnames, names in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for n in sorted(names):
                p = Path(dirpath, n)
                self.files.append(p.relative_to(root).as_posix())

    def text(self, rel: str) -> str:
        if rel not in self._text:
            try:
                p = self.root / rel
                self._text[rel] = p.read_text(encoding="utf-8", errors="replace") if p.stat().st_size <= MAX_BYTES else ""
            except OSError:
                self._text[rel] = ""
        return self._text[rel]

    def lines(self, rel: str) -> list[str]:
        return self.text(rel).splitlines()

    def named(self, pattern: str) -> list[str]:
        rx = re.compile(pattern)
        return [f for f in self.files if rx.search(f)]

    def workflows(self) -> list[str]:
        return [f for f in self.files if re.match(r"\.github/workflows/[^/]+\.ya?ml$", f)]

    def test_files(self) -> list[str]:
        out = []
        for f in self.files:
            ext = os.path.splitext(f)[1]
            if ext not in CODE_EXT or "scripts/delivery/" in f:  # the delivery scripts are tools, not tests
                continue
            base = os.path.basename(f)
            if (re.search(r"\.(test|spec)\.[a-z]+$", base) or re.match(r"test_.*\.py$", base) or base.endswith("_test.py")
                    or base.endswith("_test.go") or base == "conftest.py"
                    or (ext == ".rs" and re.search(r"(^|/)tests/", f))):
                out.append(f)
            elif ext == ".rs" and "#[test]" in self.text(f):
                out.append(f)
        return out

    def command_files(self) -> list[str]:
        """Files that hold test commands: workflows, make/just files, package.json, gate.json, project scripts."""
        out = []
        for f in self.files:
            base = os.path.basename(f)
            if f.startswith(".github/workflows/") and base.endswith((".yml", ".yaml")):
                out.append(f)
            elif base in ("Makefile", "makefile", "justfile", "package.json", "gate.json", "config.json") and \
                    (base != "config.json" or f == ".delivery/config.json"):
                out.append(f)
            elif f.startswith("scripts/") and not f.startswith("scripts/delivery/") and f.endswith((".sh", ".bash", ".mk")):
                out.append(f)
        return out


class Report:
    def __init__(self):
        self.breaks: dict[str, list[tuple[str, int, str]]] = {g: [] for g in GUARDRAILS}

    def add(self, g: str, path: str, line: int, msg: str):
        self.breaks[g].append((path, line, msg))


def is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(("#", "//", "*", "/*"))


# ---------------------------------------------------------------- config


def load_config(root: Path, path: str | None = None) -> dict:
    p = Path(path) if path else root / ".delivery" / "config.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise ValueError("%s is not readable JSON: %s" % (p, e))
    return data if isinstance(data, dict) else {}


def settings(cfg: dict) -> dict:
    ci = cfg.get("ci") if isinstance(cfg.get("ci"), dict) else {}
    tg = ci.get("test_guardrails") if isinstance(ci.get("test_guardrails"), dict) else {}
    mode = tg.get("mode", "warn")
    if mode not in ("warn", "block"):
        raise ValueError("ci.test_guardrails.mode must be \"warn\" or \"block\", not %r" % (mode,))
    off = tg.get("off") or []
    if not isinstance(off, list) or not all(isinstance(x, str) and re.fullmatch(r"G[1-7]", x) for x in off):
        raise ValueError("ci.test_guardrails.off must be a list of G1 to G7")
    reasons = tg.get("reasons") if isinstance(tg.get("reasons"), dict) else {}
    jobs = ci.get("jobs") if isinstance(ci.get("jobs"), dict) else {}
    return {"mode": mode, "off": off, "reasons": reasons, "jobs": jobs,
            "default_branch": cfg.get("default_branch") if isinstance(cfg.get("default_branch"), str) else None}


def limits_for(st: dict, rep: Report) -> dict:
    """The per-kind limits: the defaults, lowered by any ci.jobs.<id>.test_timeout_s; a higher value is a break."""
    limits = dict(TEST_LIMITS_S)
    for job, conf in st["jobs"].items():
        t = conf.get("test_timeout_s") if isinstance(conf, dict) else None
        if not isinstance(t, dict):
            continue
        for kind, val in t.items():
            if kind not in TEST_LIMITS_S or not isinstance(val, int) or isinstance(val, bool):
                continue
            if val > TEST_LIMITS_S[kind]:
                rep.add("G1", ".delivery/config.json", 1,
                        "ci.jobs.%s.test_timeout_s.%s is %d s; it may only lower the %d s limit" % (job, kind, val, TEST_LIMITS_S[kind]))
            elif val >= 1:
                limits[kind] = min(limits[kind], val)
    return limits


# ---------------------------------------------------------------- helpers


def kind_of(path: str) -> str:
    p = path.lower()
    if "e2e" in p or "playwright" in p:
        return "e2e"
    if "integration" in p:
        return "integration"
    return "unit"


def num(expr: str) -> float | None:
    """A simple numeric expression (digits, _, *, +, spaces) as a number, or None."""
    expr = expr.strip().rstrip(",").replace("_", "")
    if not expr or not re.fullmatch(r"[\d\s*+.]+", expr):
        return None
    try:
        return float(eval(expr, {"__builtins__": {}}, {}))  # only digits and * + . reach here
    except Exception:
        return None


def balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index of the bracket that closes the one at `start`, skipping strings; -1 when none."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "\"'`":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def top_level_items(body: str) -> int:
    """Count the comma-separated items at the top level of a bracket body."""
    depth, items, i, n, seen = 0, 0, 0, len(body), False
    while i < n:
        c = body[i]
        if c in "\"'`":
            j = i + 1
            while j < n and body[j] != c:
                j += 2 if body[j] == "\\" else 1
            i, seen = j, True
        elif c in "([{":
            depth, seen = depth + 1, True
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            items += 1 if seen else 0
            seen = False
        elif c == "#" and depth >= 0 and (i == 0 or body[i - 1] in " \t\n"):
            while i < n and body[i] != "\n":
                i += 1
        elif c == "/" and body[i:i + 2] == "//":
            while i < n and body[i] != "\n":
                i += 1
        elif not c.isspace():
            seen = True
        i += 1
    return items + (1 if seen else 0)


def line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


# ---------------------------------------------------------------- G1


def g1(repo: Repo, rep: Report, limits: dict):
    # vitest / jest / playwright configs
    for f in repo.named(r"(^|/)(vitest|jest|playwright)\.[^/]*config\.[cm]?[jt]s$|(^|/)vite\.config\.[cm]?[jt]s$"):
        base = os.path.basename(f)
        text = repo.text(f)
        if base.startswith("vite.config") and "test" not in text:
            continue
        pw = base.startswith("playwright")
        kind = "e2e" if pw else kind_of(f)
        key = "timeout" if pw else "testTimeout"
        found = []
        for m in re.finditer(r"(?<![\w.])%s\s*:\s*([^\n,}]+)" % key, text):
            ls = text.rfind("\n", 0, m.start()) + 1
            found.append((len(text[ls:m.start()]) - len(text[ls:m.start()].lstrip()), m.start(), m.group(1)))
        if not found:
            for m in re.finditer(r"\bsetTimeout\s*\(\s*(\d[\d_*+\s]*)\)", text) if not pw else []:
                found.append((0, m.start(), m.group(1)))
        if not found:
            rep.add("G1", f, 1, "%s has no %s (%s limit %d s)" % (base, key, kind, limits[kind]))
            continue
        _, pos, expr = min(found)
        ms = num(re.sub(r"//.*", "", expr))
        if ms is None:
            rep.add("G1", f, line_of(text, pos), "%s is not a plain number" % key)
        elif ms > limits[kind] * 1000:
            rep.add("G1", f, line_of(text, pos), "%s %g s is over the %s limit of %d s" % (key, ms / 1000, kind, limits[kind]))
    # jest configured in package.json
    for f in repo.named(r"(^|/)package\.json$"):
        text = repo.text(f)
        if '"jest"' in text and "testTimeout" not in text and not repo.named(r"(^|/)jest\.[^/]*config\."):
            rep.add("G1", f, 1, "jest has no testTimeout")
    # per-test overrides in test files
    for f in repo.test_files():
        if os.path.splitext(f)[1] not in (".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs"):
            continue
        kind = kind_of(f)
        lim = limits[kind] * 1000
        for i, line in enumerate(repo.lines(f), 1):
            if is_comment(line):
                continue
            for rx in (r"\b(?:test|jest|vi)\.setTimeout\s*\(\s*(\d[\d_*+\s]*)\)",
                       r"^\s*\}\s*,\s*(\d[\d_]*)\s*\)\s*;?\s*$", r"\{\s*timeout\s*:\s*(\d[\d_*+\s]*)\}\s*\)",
                       r"\btestTimeout\s*:\s*(\d[\d_*+\s]*)"):
                m = re.search(rx, line)
                v = num(m.group(1)) if m else None
                if v is not None and v > lim:
                    rep.add("G1", f, i, "test timeout %g s is over the %s limit of %d s" % (v / 1000, kind, limits[kind]))
    # pytest
    cfgs = [f for f in repo.files if os.path.basename(f) in ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml")
            and re.search(r"\[(tool\.)?pytest(\.ini_options)?\]", repo.text(f))]
    if cfgs or repo.named(r"(^|/)(test_[^/]*|[^/]*_test)\.py$"):
        ok = False
        for f in cfgs:
            text = repo.text(f)
            m = re.search(r"(?m)^\s*timeout\s*=\s*(\d+(?:\.\d+)?)", text) or re.search(r"--timeout[= ](\d+(?:\.\d+)?)", text)
            if m:
                ok = True
                kind = kind_of(f)
                if float(m.group(1)) > limits[kind]:
                    rep.add("G1", f, line_of(text, m.start()), "pytest timeout %s s is over the %s limit of %d s" % (m.group(1), kind, limits[kind]))
        if not ok:
            rep.add("G1", cfgs[0] if cfgs else "conftest.py", 1, "pytest has no timeout (pytest-timeout: `timeout = N`)")
        for f in repo.test_files():
            if f.endswith(".py"):
                for i, line in enumerate(repo.lines(f), 1):
                    m = re.search(r"pytest\.mark\.timeout\(\s*(\d+(?:\.\d+)?)", line)
                    if m and float(m.group(1)) > limits[kind_of(f)]:
                        rep.add("G1", f, i, "timeout mark %s s is over the %s limit" % (m.group(1), kind_of(f)))
    # go
    gotests = repo.named(r"_test\.go$")
    if gotests:
        cmds = []
        for f in repo.command_files():
            for i, line in enumerate(repo.lines(f), 1):
                if re.search(r"\bgo test\b", line) and not is_comment(line):
                    cmds.append((f, i, line))
        if not cmds:
            rep.add("G1", gotests[0], 1, "go tests exist but no `go test -timeout` command was found")
        for f, i, line in cmds:
            m = re.search(r"-timeout[= ](\d+(?:\.\d+)?)(ms|s|m|h)?", line)
            if not m:
                rep.add("G1", f, i, "`go test` without -timeout")
                continue
            secs = float(m.group(1)) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, None: 1}[m.group(2)]
            kind = "e2e" if "e2e" in line else "integration" if "integration" in line else "unit"
            if secs > limits[kind]:
                rep.add("G1", f, i, "go test -timeout %g s is over the %s limit of %d s" % (secs, kind, limits[kind]))
    # rust
    rust = [f for f in repo.test_files() if f.endswith(".rs")]
    if rust or repo.named(r"(^|/)Cargo\.toml$") and any("cargo test" in repo.text(f) for f in repo.command_files()):
        nex = repo.named(r"(^|/)\.config/nextest\.toml$|(^|/)nextest\.toml$")
        good = False
        for f in nex:
            text = repo.text(f)
            m = re.search(r"slow-timeout\s*=\s*\{([^}]*)\}", text)
            if not m:
                m2 = re.search(r"(?m)^\s*slow-timeout\.period\s*=", text)
                if m2:
                    m = re.search(r"slow-timeout\.period\s*=\s*\"(\d+)s\"[\s\S]*?terminate-after\s*=\s*(\d+)", text)
                    if m:
                        good = True
                        if int(m.group(1)) * int(m.group(2)) > limits["unit"]:
                            rep.add("G1", f, line_of(text, m.start()), "nextest slow-timeout is over the unit limit of %d s" % limits["unit"])
                        continue
                rep.add("G1", f, 1, "nextest has no slow-timeout with terminate-after")
                continue
            body = m.group(1)
            p = re.search(r"period\s*=\s*\"(\d+)(ms|s|m)\"", body)
            t = re.search(r"terminate-after\s*=\s*(\d+)", body)
            if not p or not t:
                rep.add("G1", f, line_of(text, m.start()), "nextest slow-timeout needs period and terminate-after")
                continue
            good = True
            secs = int(p.group(1)) * {"ms": 0.001, "s": 1, "m": 60}[p.group(2)] * int(t.group(1))
            if secs > limits["unit"]:
                rep.add("G1", f, line_of(text, m.start()), "nextest slow-timeout %g s is over the unit limit of %d s" % (secs, limits["unit"]))
        if not good and not nex:
            site = next(((f, i) for f in repo.command_files() for i, ln in enumerate(repo.lines(f), 1)
                         if re.search(r"\bcargo test\b", ln) and "--doc" not in ln and not is_comment(ln)), None)
            rep.add("G1", site[0] if site else rust[0], site[1] if site else 1,
                    "plain `cargo test` has no per-test timeout; use cargo nextest with slow-timeout and terminate-after")


# ---------------------------------------------------------------- G2


def workflow_jobs(text: str) -> list[tuple[str, int, int, list[str]]]:
    """(job id, 1-based line, indent, lines) of each job in a workflow, by indentation."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"jobs\s*:\s*$", ln)), None)
    if start is None:
        return []
    out, cur, indent = [], None, None
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith("#"):
            if cur:
                cur[3].append(ln)
            continue
        ind = len(ln) - len(ln.lstrip())
        if ind == 0:
            break
        if indent is None:
            indent = ind
        m = re.match(r"\s*([A-Za-z0-9_-]+)\s*:\s*$", ln)
        if ind == indent and m:
            cur = [m.group(1), i + 1, ind, []]
            out.append(cur)
        elif cur:
            cur[3].append(ln)
    return [tuple(c) for c in out]  # type: ignore[misc]


def g2(repo: Repo, rep: Report, st: dict):
    for f in repo.workflows():
        for job, line, ind, body in workflow_jobs(repo.text(f)):
            if any(re.match(r"\s{%d}uses\s*:" % (ind + 2), b) for b in body):
                continue  # a reusable workflow call cannot set it
            cfg = st["jobs"].get(job) if isinstance(st["jobs"].get(job), dict) else {}
            cmin = cfg.get("timeout_minutes")
            limit = JOB_LIMIT_MIN
            if isinstance(cmin, int) and not isinstance(cmin, bool):
                if cmin > JOB_LIMIT_MIN:
                    rep.add("G2", ".delivery/config.json", 1, "ci.jobs.%s.timeout_minutes is %d; the limit is %d" % (job, cmin, JOB_LIMIT_MIN))
                else:
                    limit = cmin
            m = next((re.match(r"\s{%d}timeout-minutes\s*:\s*(\S+)" % (ind + 2), b) for b in body
                      if re.match(r"\s{%d}timeout-minutes\s*:" % (ind + 2), b)), None)
            if m is None:
                if not (isinstance(cmin, int) and not isinstance(cmin, bool) and cmin <= JOB_LIMIT_MIN):
                    rep.add("G2", f, line, "job %s sets no timeout-minutes" % job)
                continue
            v = num(m.group(1).split("#")[0])
            if v is None:
                rep.add("G2", f, line, "job %s: timeout-minutes %s is not a number" % (job, m.group(1)))
            elif v > limit:
                rep.add("G2", f, line, "job %s: timeout-minutes %g is over %d" % (job, v, limit))


# ---------------------------------------------------------------- G3


def g3(repo: Repo, rep: Report):
    for f in repo.named(r"(^|/)playwright\.[^/]*config\.[cm]?[jt]s$"):
        for i, ln in enumerate(repo.lines(f), 1):
            m = re.match(r"\s*retries\s*:\s*(.+)", ln)
            if m and re.search(r"[1-9]", m.group(1).split("//")[0]):
                rep.add("G3", f, i, "Playwright retries: %s" % m.group(1).strip().rstrip(","))
    pat = [(r"--reruns?\b(?!\s*=?\s*0\b)", "pytest --reruns"), (r"pytest-rerunfailures|pytest-retry|pytest-flaky", "a flaky/rerun plugin"),
           (r"--retries[= ]+[1-9]", "--retries"), (r"nick-fields/retry|retry-action", "a retry action"),
           (r"--onlyFailures|--rerun-failed|rerun_failed|--rerun-failures|retry_failed", "a re-run of failed files")]
    for f in repo.command_files() + repo.named(r"(^|/)(pytest\.ini|tox\.ini|setup\.cfg|pyproject\.toml|requirements[^/]*\.txt)$"):
        for i, ln in enumerate(repo.lines(f), 1):
            if is_comment(ln):
                continue
            for rx, what in pat:
                if re.search(rx, ln):
                    rep.add("G3", f, i, what)
                    break
    for f in repo.named(r"(^|/)nextest\.toml$"):
        for i, ln in enumerate(repo.lines(f), 1):
            m = re.match(r"\s*retries\s*=\s*(.+)", ln)
            if m and re.search(r"[1-9]", m.group(1)):
                rep.add("G3", f, i, "nextest retries: %s" % m.group(1).strip())
    for f in repo.test_files():
        for i, ln in enumerate(repo.lines(f), 1):
            if is_comment(ln):
                continue
            if re.search(r"\bjest\.retryTimes\s*\(\s*[1-9]", ln) or re.search(r"pytest\.mark\.flaky|@flaky\b", ln):
                rep.add("G3", f, i, "a retry in a test file")


# ---------------------------------------------------------------- G4

SLEEP_RX = re.compile(
    r"\btime\.sleep\s*\(|\basyncio\.sleep\s*\(|\bwaitForTimeout\s*\(|\btime\.Sleep\s*\(|\bthread::sleep\s*\(|"
    r"\btokio::time::sleep\s*\(|\bawait\s+sleep\s*\(|\bnew Promise\([^)]*setTimeout|"
    r"\bsetTimeout\s*\(\s*(?:resolve|res|r|done|\(\)\s*=>\s*(?:resolve|res|r)\b)|^\s*(?:std::)?sleep\s*\(")
LOOP_RX = re.compile(r"^\s*(?:while\s+True\s*:|while\s*\(\s*true\s*\)|while\s+true\b|loop\s*\{|for\s*\{)")
DEADLINE_RX = re.compile(r"deadline|timeout|elapsed|Instant|monotonic|time\.time\(|Date\.now|performance\.now|attempts|"
                         r"max_|range\(|time\.Since|time\.After|ctx\.Done|ctx\.Err|retries|tries", re.I)


def g4(repo: Repo, rep: Report):
    for f in repo.test_files():
        lines = repo.lines(f)
        hits = []
        for i, ln in enumerate(lines, 1):
            if is_comment(ln):
                continue
            if SLEEP_RX.search(ln):
                hits.append(i)
            elif LOOP_RX.match(ln) and not DEADLINE_RX.search("\n".join(lines[i - 1:i + 12])):
                hits.append(i)
        if hits:
            rep.add("G4", f, hits[0], "%d sleep or open-ended wait%s" % (len(hits), "" if len(hits) == 1 else "s"))


# ---------------------------------------------------------------- G5


def g5(repo: Repo, rep: Report):
    for f in repo.test_files():
        text = repo.text(f)
        ext = os.path.splitext(f)[1]
        if ext in (".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs"):
            for m in re.finditer(r"\.each\s*(\(|`)", text):
                if m.group(1) == "(":
                    p = text.find("[", m.end() - 1, m.end() + 3)
                    if p < 0:
                        continue
                    q = balanced(text, p, "[", "]")
                    n = top_level_items(text[p + 1:q]) if q > 0 else 0
                else:
                    q = text.find("`", m.end())
                    rows = [r for r in text[m.end():q].splitlines() if "|" in r] if q > 0 else []
                    n = max(0, len(rows) - 1)
                if n > MAX_CASES:
                    rep.add("G5", f, line_of(text, m.start()), "%d cases in one .each table" % n)
        elif ext == ".py":
            for m in re.finditer(r"pytest\.mark\.parametrize\s*\(", text):
                q = balanced(text, m.end() - 1, "(", ")")
                if q < 0:
                    continue
                args = text[m.end():q]
                p = re.search(r"[\[(]", args[args.find(",") + 1:] if "," in args else "")
                if not p:
                    continue
                s = args.find(",") + 1 + p.start()
                op = args[s]
                e = balanced(args, s, op, "]" if op == "[" else ")")
                n = top_level_items(args[s + 1:e]) if e > 0 else 0
                if n > MAX_CASES:
                    rep.add("G5", f, line_of(text, m.start()), "%d cases in one parametrize list" % n)
        elif ext == ".go":
            for fm in re.finditer(r"(?m)^func Test\w*\(", text):
                nxt = re.search(r"(?m)^func ", text[fm.end():])
                body_end = fm.end() + nxt.start() if nxt else len(text)
                for m in re.finditer(r"\[\]\s*(?:struct\s*\{[^}]*\}|\w+(?:\.\w+)?)\s*\{", text[fm.end():body_end]):
                    s = fm.end() + m.end() - 1
                    q = balanced(text, s, "{", "}")
                    n = top_level_items(text[s + 1:q]) if q > 0 else 0
                    if n > MAX_CASES:
                        rep.add("G5", f, line_of(text, s), "%d rows in one table test" % n)
        elif ext == ".rs":
            for m in re.finditer(r"#\[rstest\]", text):
                nxt = re.search(r"\bfn\s", text[m.end():])
                seg = text[m.end(): m.end() + nxt.start()] if nxt else ""
                n = len(re.findall(r"#\[case", seg))
                if n > MAX_CASES:
                    rep.add("G5", f, line_of(text, m.start()), "%d #[case] rows" % n)


# ---------------------------------------------------------------- G6

MUTATION_RX = re.compile(r"stryker|mutmut|cargo[ -]mutants|go-mutesting|mutation[_ -]?(?:pass|test|run)s?|run[_-]mutation", re.I)


def triggers(text: str, default_branches) -> tuple[bool, str]:
    """(runs on a pull request or a non-default push, why) from the `on:` block."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"(on|\"on\"|'on')\s*:", ln)), None)
    if start is None:
        return False, ""
    head = lines[start]
    inline = head.split(":", 1)[1].strip()
    if inline:
        names = re.findall(r"[a-z_]+", inline)
        return ("pull_request" in names, "pull_request") if "pull_request" in names else (False, "")
    block = []
    for ln in lines[start + 1:]:
        if ln.strip() and not ln.startswith((" ", "\t", "#")):
            break
        block.append(ln)
    body = "\n".join(block)
    if re.search(r"(?m)^\s*-?\s*pull_request(_target)?\b", body):
        return True, "pull_request"
    m = re.search(r"(?m)^(\s*)push\s*:(.*)$", body)
    if m or re.search(r"(?m)^\s*-\s*push\b", body):
        if not m:
            return True, "push to every branch"
        sub = []
        ind = len(m.group(1))
        for ln in body[m.end():].splitlines()[1:]:
            if ln.strip() and len(ln) - len(ln.lstrip()) <= ind:
                break
            sub.append(ln)
        sb = "\n".join(sub)
        if "branches-ignore" in sb:
            return True, "push to non-default branches"
        bm = re.search(r"branches\s*:\s*(\[[^\]]*\]|(?:\n\s*-\s*\S+)+)", sb)
        if not bm:
            return True, "push to every branch"
        names = re.findall(r"[\w./*-]+", re.sub(r"^branches\s*:", "", bm.group(0)))
        if any(n not in default_branches for n in names):
            return True, "push to a non-default branch"
    return False, ""


def g6(repo: Repo, rep: Report, st: dict):
    defaults = (st["default_branch"],) if st["default_branch"] else DEFAULT_BRANCHES
    pr_flows = []
    for f in repo.workflows():
        text = repo.text(f)
        hit, why = triggers(text, defaults)
        if not hit:
            continue
        pr_flows.append(f)
        for i, ln in enumerate(text.splitlines(), 1):
            if is_comment(ln) or "no-mutants" in ln or "no-mutation" in ln:
                continue
            if MUTATION_RX.search(ln):
                rep.add("G6", f, i, "a mutation run in a workflow triggered on %s" % why)
                break
        for i, ln in enumerate(text.splitlines(), 1):
            m = re.search(r"(?:PROPTEST_CASES|HYPOTHESIS_MAX_EXAMPLES|NUM_RUNS)\s*[:=]\s*[\"']?(\d+)", ln)
            if m and int(m.group(1)) > (256 if "PROPTEST" in ln else 100):
                rep.add("G6", f, i, "%s many-run property tests on %s" % (m.group(1), why))
    if not pr_flows:
        return
    for f in repo.test_files() + repo.named(r"(^|/)(conftest\.py|pyproject\.toml|[^/]*config\.[cm]?[jt]s)$"):
        for i, ln in enumerate(repo.lines(f), 1):
            if is_comment(ln):
                continue
            m = re.search(r"\bnumRuns\s*:\s*(\d[\d_]*)", ln)
            if m and int(m.group(1).replace("_", "")) > 100:
                rep.add("G6", f, i, "fast-check numRuns %s runs on pull requests" % m.group(1))
            m = re.search(r"\bmax_examples\s*=\s*(\d+)", ln)
            if m and int(m.group(1)) > 100:
                rep.add("G6", f, i, "hypothesis max_examples %s runs on pull requests" % m.group(1))
            m = re.search(r"(?:\bcases\s*:\s*|with_cases\(\s*)(\d[\d_]*)", ln)
            if m and f.endswith(".rs") and int(m.group(1).replace("_", "")) > 256:
                rep.add("G6", f, i, "proptest cases %s run on pull requests" % m.group(1))


# ---------------------------------------------------------------- G7

TIMES_RX = re.compile(r"ci-run-times|ci_run_times|junit|test-results|test-times|test_times|timings?\.json|durations?\.json", re.I)


def g7(repo: Repo, rep: Report):
    if not (repo.test_files() or repo.named(r"_test\.go$")):
        return
    for f in repo.workflows():
        lines = repo.lines(f)
        for i, ln in enumerate(lines):
            if "upload-artifact" in ln and TIMES_RX.search("\n".join(lines[i:i + 8])):
                return
    wf = repo.workflows()
    rep.add("G7", wf[0] if wf else ".github/workflows", 1,
            "no workflow uploads test times (ci-run-times, a JUnit report or a timing JSON)")


# ---------------------------------------------------------------- run


def scan(root: Path, cfg: dict) -> dict:
    """The report: {mode, off, results: {G1: {state, breaks:[...]}}, notes: [...]}."""
    st = settings(cfg)
    repo = Repo(root)
    rep = Report()
    limits = limits_for(st, rep)
    g1(repo, rep, limits)
    g2(repo, rep, st)
    g3(repo, rep)
    g4(repo, rep)
    g5(repo, rep)
    g6(repo, rep, st)
    g7(repo, rep)
    notes, results = [], {}
    for g, title in GUARDRAILS.items():
        off = g in st["off"]
        reason = str(st["reasons"].get(g, "")).strip()
        if off and reason:
            results[g] = {"title": title, "state": "off", "reason": reason, "count": 0, "breaks": []}
            continue
        if off:
            notes.append("%s is turned off without a reason in ci.test_guardrails.reasons; it stays on" % g)
        items = [{"file": p, "line": ln, "message": m} for p, ln, m in rep.breaks[g]]
        results[g] = {"title": title, "state": "break" if items else "pass", "count": len(items), "breaks": items}
    return {"mode": st["mode"], "results": results, "notes": notes}


def failed(report: dict) -> bool:
    return bool(report["notes"]) or any(r["state"] == "break" for r in report["results"].values())


def render(report: dict) -> str:
    out = ["test guardrails (DL-99), mode %s" % report["mode"]]
    for g, r in report["results"].items():
        if r["state"] == "pass":
            out.append("  %s PASS  %s" % (g, r["title"]))
        elif r["state"] == "off":
            out.append("  %s OFF   %s (reason: %s)" % (g, r["title"], r["reason"]))
        else:
            out.append("  %s %d break%s  %s" % (g, r["count"], "" if r["count"] == 1 else "s", r["title"]))
            for b in r["breaks"][:SHOWN]:
                out.append("      %s:%d  %s" % (b["file"], b["line"], b["message"]))
            if r["count"] > SHOWN:
                out.append("      ... and %d more" % (r["count"] - SHOWN))
    for n in report["notes"]:
        out.append("  NOTE %s" % n)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="test_guardrails.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", help="repository root (default: the current directory)")
    ap.add_argument("--config", help="config file (default: <root>/.delivery/config.json)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--mode", choices=("warn", "block"), help="override ci.test_guardrails.mode")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        report = scan(root, load_config(root, args.config))
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    if args.mode:
        report["mode"] = args.mode
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 1 if report["mode"] == "block" and failed(report) else 0


if __name__ == "__main__":
    sys.exit(main())
