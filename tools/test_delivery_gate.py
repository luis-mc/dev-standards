#!/usr/bin/env python3
"""Prove the branch-gate scripts behave as CONTRACT.md says.

Covers branch_gate.py, gate_verify.py, fast_guards.py, join.py, agent_setup.sh,
the pre-push hook, the per-track gate.json files and the guard starters. Every
scenario builds throwaway git repositories in a temp directory: a bare "origin",
a working clone with a pnpm-workspace-style layout (directories and a
pnpm-workspace.yaml; the step commands are a tiny Python script that logs what
ran and exits 0, or 1 when named in GATE_TEST_FAIL), the delivery scripts copied
from the plugin assets, and a test gate.json.

"Every check must be able to fail" is proved two ways. Most scenarios contain
both sides of a rule (trusted and stale, clean and dirty), so a check that
always passed would break the other side. Then the mutation pass copies the
scripts, breaks one rule in the copy (an `if` made unconditional, a flag
dropped) and requires the scenario that guards that rule to report a failure.
A mutant that goes undetected is a check that cannot fail, and fails this run.

Run:  python3 tools/test_delivery_gate.py [--no-mutants] [--shard I/N] [--no-scenarios] [-k SUBSTRING]
Exit: 0 all passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import io
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLING = REPO / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling"
SHARED = TOOLING / "shared"
PY = Path(sys.executable).as_posix()

sys.path.insert(0, str(SHARED / "scripts/delivery"))
import delivery_common as dc  # noqa: E402  (the module under test, for unit checks)

SCRIPT_FILES = [
    "delivery_common.py", "branch_gate.py", "gate_verify.py", "fast_guards.py",
    "join.py", "agent_setup.sh", "tools.json", "e2e_push_check.py",
]
TRACKS = {
    "ts": "pnpm-workspace",
    "go": "go-modules",
    "rust": "cargo-workspace",
    "dotnet": "dotnet-sln",
}

# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="delivery-gate-test-"))
_GITCONFIG = _TMP_ROOT / "gitconfig"
_GITCONFIG.write_text(
    "[user]\n\tname = Gate Test\n\temail = gate@example.com\n"
    "[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n\tlongpaths = true\n"
    "[advice]\n\tdetachedHead = false\n",
    encoding="utf-8",
)


def env_with(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GATE_TEST_FAIL", "GIT_PREFIX", "CARGO_TARGET_DIR"):
        env.pop(var, None)
    env.update(
        GIT_CONFIG_GLOBAL=str(_GITCONFIG),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        PYTHONIOENCODING="utf-8",
        NO_PROXY="127.0.0.1,localhost",
        no_proxy="127.0.0.1,localhost",
    )
    if extra:
        env.update(extra)
    return env


def rmtree(path: Path) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onerror=onerror)


class R:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.code = proc.returncode
        self.out = proc.stdout.decode("utf-8", "replace")
        self.err = proc.stderr.decode("utf-8", "replace")

    @property
    def text(self) -> str:
        return self.out + self.err


def run(cmd: list, cwd: Path | None = None, extra_env: dict | None = None, input_text: str | None = None) -> R:
    return R(
        subprocess.run(
            [str(c) for c in cmd],
            cwd=cwd,
            env=env_with(extra_env),
            capture_output=True,
            input=input_text.encode() if input_text is not None else None,
            check=False,
        )
    )


class MutantStop(BaseException):
    """Raised by the first failed check of a scenario that runs as a mutant: the mutant
    is caught, and the rest of the scenario is not worth the time. A BaseException so
    that no `except Exception` inside a scenario swallows it."""


class T:
    """Records the checks of one scenario. A quiet one (a mutant run) stops at the
    first failed check; a normal run checks everything."""

    def __init__(self, name: str, quiet: bool = False):
        self.name, self.quiet = name, quiet
        self.total = 0
        self.failures: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.total += 1
        if not ok:
            self.failures.append(label)
            if self.quiet:
                raise MutantStop(label)
        if not self.quiet:
            line = "%s  %s: %s" % ("PASS" if ok else "FAIL", self.name, label)
            if not ok and detail:
                line += "\n        " + detail.strip().replace("\n", "\n        ")[:900]
            print(line)
        return ok

    def eq(self, label: str, actual, expected) -> bool:
        return self.check(label, actual == expected, "expected %r\n   actual %r" % (expected, actual))

    def has(self, label: str, text: str, needle: str) -> bool:
        return self.check(label, needle in text, "%r not in:\n%s" % (needle, text))


class Box:
    """A bare origin plus a working clone holding the delivery scripts."""

    INIT_FILES = {
        ".gitignore": ".delivery/\n",
        "pnpm-workspace.yaml": "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
        "pnpm-lock.yaml": "lock\nl1\nl2\n",
        "package.json": "{}\n",
        "apps/web/index.txt": "web\n",
        "apps/web/shared.txt": "one\ntwo\nthree\n",
        "apps/api/index.txt": "api\n",
        "packages/ui/index.txt": "ui\n",
        "packages/core/index.txt": "core\n",
        "docs/readme.txt": "docs\n",
    }

    STEP_SCRIPT = (
        "import json, os, sys, time\n"
        "name, args = sys.argv[1], sys.argv[2:]\n"
        "os.makedirs('.delivery', exist_ok=True)\n"
        "with open('.delivery/ran.log', 'a') as f:\n"
        "    f.write(json.dumps([name] + args) + '\\n')\n"
        # Where the step ran and what it could see, in a file outside the checkout (a
        # step run in a temporary worktree leaves nothing behind there).
        "cl = os.environ.get('GATE_TEST_CWDLOG')\n"
        "if cl:\n"
        "    nm = 'node_modules'\n"
        "    here = os.path.realpath('.')\n"
        "    rec = {'step': name, 'args': args, 'cwd': os.getcwd().replace(os.sep, '/'),\n"
        "           'cargo': os.environ.get('CARGO_TARGET_DIR'),\n"
        "           'nm': sorted(os.listdir(nm)) if os.path.isdir(nm) else None,\n"
        "           'nm_link': os.path.isdir(nm) and os.path.realpath(nm) != os.path.join(here, nm),\n"
        "           'deep': sorted(os.listdir('apps/web/node_modules')) if os.path.isdir('apps/web/node_modules') else None,\n"
        "           'ghost': os.path.exists('apps/ghost/node_modules')}\n"
        "    if os.environ.get('GATE_TEST_NMWRITE') and os.path.isdir(nm):\n"
        "        open(os.path.join(nm, 'probe.txt'), 'w').write('p')\n"
        "    open(cl, 'a').write(json.dumps(rec) + '\\n')\n"
        "print('[%s] stdout' % name, flush=True)\n"
        "print('[%s] stderr' % name, file=sys.stderr, flush=True)\n"
        "if name == 'guards' and os.path.exists('BAD_GUARD'):\n"
        "    print('BAD_GUARD file present', flush=True)\n"
        "    sys.exit(1)\n"
        "if name in os.environ.get('GATE_TEST_NOISE', '').split(','):\n"
        "    for i in range(1, 101):\n"
        "        print('noise line %03d' % i, flush=True)\n"
        "if os.environ.get('GATE_TEST_MARK'):\n"
        "    print('mark ' + os.environ['GATE_TEST_MARK'], flush=True)\n"
        "time.sleep(float(os.environ.get('GATE_TEST_HOLD', '0')))\n"
        "sys.exit(1 if name in os.environ.get('GATE_TEST_FAIL', '').split(',') else 0)\n"
    )

    # Reports how much it could read from its stdin (0 when stdin is closed).
    STDIN_SCRIPT = "import sys\nprint('stdin bytes', len(sys.stdin.read()), flush=True)\n"

    # A step that never finishes on its own and leaves a child behind that would
    # outlive it: the child appends to .delivery/child.beat every 0.1 s for 30 s.
    SLOW_SCRIPT = (
        "import os, subprocess, sys\n"
        "os.makedirs('.delivery', exist_ok=True)\n"
        "print('slow step started', flush=True)\n"
        "subprocess.Popen([sys.executable, 'scripts/delivery/_beat.py']).wait()\n"
    )
    BEAT_SCRIPT = (
        "import time\n"
        "for _ in range(300):\n"
        "    with open('.delivery/child.beat', 'a') as f:\n"
        "        f.write('x')\n"
        "    time.sleep(0.1)\n"
    )
    # Fails (exit 1) the way a frozen install does when the lockfile is stale.
    LOCK_SCRIPT = (
        "import sys\n"
        "text = open('pnpm-lock.yaml', encoding='utf-8').read()\n"
        "if 'STALE' in text:\n"
        "    print('ERR_PNPM_OUTDATED_LOCKFILE: lockfile is not up to date with package.json', file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )

    def __init__(self, shared: Path = SHARED, gate_json: dict | None = None, hooks: bool = True):
        self.root = Path(tempfile.mkdtemp(prefix="box-", dir=_TMP_ROOT))
        self.origin = self.root / "origin.git"
        self.work = self.root / "work"
        run(["git", "init", "-q", "--bare", "-b", "main", self.origin])
        self.work.mkdir()
        self.g("init", "-q", "-b", "main")
        self.g("remote", "add", "origin", self.origin.as_posix())
        for rel, text in self.INIT_FILES.items():
            self.write(rel, text)
        d = self.work / "scripts/delivery"
        d.mkdir(parents=True)
        for name in SCRIPT_FILES:
            self.copy_text(shared / "scripts/delivery" / name, d / name)
        for fname, body in (("_t.py", self.STEP_SCRIPT), ("_slow.py", self.SLOW_SCRIPT),
                            ("_beat.py", self.BEAT_SCRIPT), ("_lock.py", self.LOCK_SCRIPT),
                            ("_stdin.py", self.STDIN_SCRIPT)):
            (d / fname).write_text(body, encoding="utf-8", newline="\n")
        (d / "gate.json").write_text(json.dumps(gate_json or self.gate_json(), indent=2) + "\n", encoding="utf-8")
        if hooks:
            (self.work / ".githooks").mkdir()
            self.copy_text(shared / ".githooks/pre-push", self.work / ".githooks/pre-push")
        for exe in (d / "agent_setup.sh", self.work / ".githooks/pre-push"):
            if exe.exists():
                exe.chmod(0o755)
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "init")
        self.commit({"docs/more.txt": "more\n"}, "more docs")
        self.g("push", "-q", "-u", "origin", "main")
        self.main_sha = self.g("rev-parse", "HEAD")

    # -- config ------------------------------------------------------------
    @staticmethod
    def step_cmd(name: str, extra: str = "") -> str:
        return ('"%s" scripts/delivery/_t.py %s %s' % (PY, name, extra)).strip()

    @classmethod
    def gate_json(cls) -> dict:
        c = cls.step_cmd
        return {
            "schema": 1,
            "track": "test",
            "default_branch": "main",
            "setup": [c("setup")],
            "packages": {"kind": "pnpm-workspace"},
            "widen_on": ["pnpm-lock.yaml", "package.json", "turbo.jsonc", ".github/", "scripts/delivery/"],
            "ui_paths": ["apps/web/", "packages/ui/"],
            "steps": [
                {"name": "typecheck", "scope": "changed+dependents",
                 "run": c("typecheck", "{changed_dirs}"), "run_full": c("typecheck", "FULL")},
                {"name": "lint", "scope": "changed+dependents",
                 "run": c("lint", "{changed_dirs}"), "run_full": c("lint", "FULL")},
                {"name": "unit", "scope": "changed",
                 "run": c("unit", "{changed_dirs}"), "run_full": c("unit", "FULL")},
                {"name": "guards", "scope": "always", "pre_push": True, "run": c("guards")},
                {"name": "secret-scan", "scope": "always", "pre_push": True,
                 "run": c("secret-scan", "{base}")},
                {"name": "e2e", "scope": "ui-changed", "run": c("e2e")},
            ],
        }

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def copy_text(src: Path, dst: Path) -> None:
        data = src.read_bytes().replace(b"\r\n", b"\n")  # a Windows checkout may have CRLF
        dst.write_bytes(data)

    def g(self, *args: str, cwd: Path | None = None, check: bool = True, input_text: str | None = None) -> str:
        r = run(["git", *args], cwd=cwd or self.work, input_text=input_text)
        if check and r.code != 0:
            raise RuntimeError("git %s failed: %s" % (" ".join(args), r.err))
        return r.out.strip()

    def write(self, rel: str, text: str) -> None:
        p = self.work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, files: dict, msg: str) -> str:
        for rel, text in files.items():
            self.write(rel, text)
        self.g("add", "-A")
        self.g("commit", "-q", "-m", msg)
        return self.g("rev-parse", "HEAD")

    def branch(self, name: str, files: dict, frm: str = "main") -> str:
        self.g("checkout", "-q", "-B", name, frm)
        return self.commit(files, "work on " + name)

    def push(self, name: str) -> None:
        self.g("push", "-q", "-u", "origin", name)

    def script(self, name: str, *args: str, env: dict | None = None) -> R:
        return run([PY, "scripts/delivery/" + name, *args], cwd=self.work, extra_env=env)

    def gate(self, *args: str, base_ref: str | None = "origin/main", env: dict | None = None) -> R:
        a = list(args)
        if base_ref:
            a = ["--base-ref", base_ref] + a
        return self.script("branch_gate.py", *a, env=env)

    def gated(self, name: str, files: dict, frm: str = "main", base_ref: str = "origin/main",
              fail: str | None = None) -> str:
        """Create a branch, gate it (publishing), push it. Returns its head."""
        head = self.branch(name, files, frm)
        self.gate(base_ref=base_ref, env={"GATE_TEST_FAIL": fail} if fail else None)
        self.push(name)
        return head

    def ran(self, setup: bool = False) -> list:
        """The step commands that ran, in order; `setup` also lists the install."""
        log = self.work / ".delivery/ran.log"
        if not log.exists():
            return []
        rows = [json.loads(line) for line in log.read_text().splitlines() if line]
        return rows if setup else [r for r in rows if r[0] != "setup"]

    def clear_log(self) -> None:
        log = self.work / ".delivery/ran.log"
        if log.exists():
            log.unlink()

    def result(self) -> dict:
        return json.loads((self.work / dc.GATE_RESULT_PATH).read_text(encoding="utf-8"))

    def remote_ref(self, ref: str) -> str | None:
        out = self.g("ls-remote", "origin", ref)
        return out.split()[0] if out else None

    def origin_git(self, *args: str) -> str:
        return run(["git", "--git-dir", self.origin.as_posix(), *args]).out.strip()

    def publish_raw(self, branch: str, text: str) -> None:
        blob = self.g("hash-object", "-w", "--stdin", input_text=text)
        tree = self.g("mktree", input_text="100644 blob %s\tgate-result.json\n" % blob)
        commit = self.g("commit-tree", tree, "-m", "raw")
        self.g("push", "-q", "--force", "origin", "%s:refs/gate-results/%s" % (commit, branch))

    def clean(self) -> bool:
        return not self.g("status", "--porcelain", "--untracked-files=normal").replace(".delivery/", "").strip()


# --------------------------------------------------------------------------
# scenarios: branch_gate.py
# --------------------------------------------------------------------------

def sc_scopes(t: T, shared: Path) -> None:
    box = Box(shared)
    box.branch("feat/web", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-publish")
    t.eq("ui package change: exit 0", r.code, 0)
    log = box.ran()
    t.eq("ui package change: every step ran, in order",
         [x[0] for x in log], ["typecheck", "lint", "unit", "guards", "secret-scan", "e2e"])
    t.eq("changed_dirs placeholder filled", log[0], ["typecheck", "apps/web"])
    t.eq("base placeholder is the merge base", log[4], ["secret-scan", box.main_sha])
    res = box.result()
    t.eq("result: contract keys present",
         sorted(res), sorted(["schema", "kind", "branch", "head", "base", "base_ref", "base_fetched", "widened",
                              "changed_dirs", "steps", "required_steps", "pass", "timed_out", "partial", "started_at",
                              "finished_at", "tool", "e2e_only", "ui_changed", "e2e"]))
    t.eq("result: branch", res["branch"], "feat/web")
    t.eq("result: head", res["head"], box.g("rev-parse", "HEAD"))
    t.eq("result: base", res["base"], box.main_sha)
    t.eq("result: base_ref", res["base_ref"], "origin/main")
    t.eq("result: changed_dirs", res["changed_dirs"], ["apps/web"])
    t.eq("result: not widened", res["widened"], False)
    t.eq("result: pass", res["pass"], True)
    t.eq("result: kind and schema", (res["kind"], res["schema"]), ("branch-gate", 1))
    t.check("result: timestamps are UTC ISO",
            all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", res[k]) for k in ("started_at", "finished_at")))
    t.check("result: tool names the script", res["tool"].startswith("branch_gate.py "))
    t.eq("result: setup is the first step", res["steps"][0]["name"], "setup")
    t.eq("result: step shape", sorted(res["steps"][1]),
         ["command", "exit_code", "log", "name", "outcome", "reason", "seconds"])
    t.check("result: command recorded with placeholders filled",
            "apps/web" in res["steps"][1]["command"] and "{" not in res["steps"][1]["command"])
    t.has("summary table printed", r.out, "outcome")
    t.has("summary table names a step", r.out, "secret-scan")

    box.branch("feat/api", {"apps/api/b.txt": "b\n"})
    box.clear_log()
    r = box.gate("--no-publish")
    t.eq("non-ui package: e2e is not run",
         [x[0] for x in box.ran()], ["typecheck", "lint", "unit", "guards", "secret-scan"])
    outcomes = {s["name"]: s["outcome"] for s in box.result()["steps"]}
    t.eq("non-ui package: e2e recorded as skip", outcomes["e2e"], "skip")
    t.eq("non-ui package: others pass", {k: v for k, v in outcomes.items() if k != "e2e"},
         {k: "pass" for k in outcomes if k != "e2e"})

    box.branch("feat/docs", {"docs/new.txt": "n\n"})
    box.clear_log()
    r = box.gate("--no-publish")
    t.eq("no package changed: only always-steps run", [x[0] for x in box.ran()], ["guards", "secret-scan"])
    outcomes = {s["name"]: s["outcome"] for s in box.result()["steps"]}
    t.eq("no package changed: scoped steps are skip",
         (outcomes["typecheck"], outcomes["lint"], outcomes["unit"], outcomes["e2e"]), ("skip",) * 4)
    t.eq("no package changed: still passes", r.code, 0)

    box.branch("feat/two", {"apps/api/c.txt": "c\n", "packages/core/c.txt": "c\n"})
    box.clear_log()
    box.gate("--no-publish")
    t.eq("several packages: sorted and space separated",
         box.ran()[0], ["typecheck", "apps/api", "packages/core"])

    box.g("checkout", "-q", "feat/web")
    box.clear_log()
    r = box.gate("--no-publish", base_ref=None)
    t.eq("default base ref is origin/<default_branch>", (r.code, box.result()["base_ref"]), (0, "origin/main"))


def sc_affected(t: T, shared: Path) -> None:
    """{affected_dirs}: the changed packages plus the packages that depend on them."""

    class AffectedBox(Box):
        INIT_FILES = {
            **Box.INIT_FILES,
            "packages/core/package.json": '{"name": "@x/core"}\n',
            "packages/ui/package.json": '{"name": "@x/ui", "dependencies": {"@x/core": "workspace:*"}}\n',
            "apps/web/package.json": '{"name": "@x/web", "devDependencies": {"@x/ui": "workspace:*"}}\n',
            "apps/api/package.json": '{"name": "@x/api", "dependencies": {"@x/core": "workspace:*", "left-pad": "1"}}\n',
        }

        @classmethod
        def gate_json(cls) -> dict:
            cfg = Box.gate_json()
            for s in cfg["steps"]:
                if s["name"] == "unit":
                    s["scope"] = "changed+dependents"
                    s["run"] = cls.step_cmd("unit", "{affected_dirs}")
            return cfg

    box = AffectedBox(shared)
    box.branch("feat/core", {"packages/core/a.txt": "a\n"})
    t.eq("a leaf package's change reaches its direct and transitive dependents",
         (box.gate("--no-publish").code, [x for x in box.ran() if x[0] == "unit"]),
         (0, [["unit", "apps/api", "apps/web", "packages/core", "packages/ui"]]))
    t.eq("... while {changed_dirs} stays the changed set",
         [x for x in box.ran() if x[0] == "typecheck"], [["typecheck", "packages/core"]])
    t.eq("... and the result records the changed set", box.result()["changed_dirs"], ["packages/core"])

    box.branch("feat/api", {"apps/api/a.txt": "a\n"})
    box.clear_log()
    box.gate("--no-publish")
    t.eq("a package nothing depends on is its own affected set",
         [x for x in box.ran() if x[0] == "unit"], [["unit", "apps/api"]])

    box.branch("feat/lock", {"pnpm-lock.yaml": "lock\nl1\nchanged\n"})
    box.clear_log()
    box.gate("--no-publish")
    t.eq("a widened gate runs run_full", [x for x in box.ran() if x[0] == "unit"], [["unit", "FULL"]])

    # the closure itself, on a cycle and on a non-pnpm kind
    root = Path(tempfile.mkdtemp(dir=_TMP_ROOT))
    for rel, text in {"a/package.json": '{"name": "a", "dependencies": {"b": "1"}}',
                      "b/package.json": '{"name": "b", "dependencies": {"a": "1"}}',
                      "c/package.json": "not json",
                      "d/package.json": '{"name": "d", "peerDependencies": {"a": "1"}}'}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    pk = ["a", "b", "c", "d"]
    t.eq("dependency cycle and peer dependency terminate", dc.affected_package_dirs(
        root, {"kind": "pnpm-workspace"}, pk, ["a"]), ["a", "b", "d"])
    t.eq("an unreadable package.json is skipped", dc.affected_package_dirs(
        root, {"kind": "pnpm-workspace"}, pk, ["c"]), ["c"])
    t.eq("other kinds have no graph: the changed set", dc.affected_package_dirs(
        root, {"kind": "go-modules"}, pk, ["a"]), ["a"])


def sc_step_env(t: T, shared: Path) -> None:
    """A step's "env" reaches its command; a bad "env" is a configuration error."""
    cfg = Box.gate_json()
    for s in cfg["steps"]:
        if s["name"] == "unit":
            s["env"] = {"GATE_TEST_FAIL": "unit"}  # the test step script fails when it sees its own name here
    box = Box(shared, gate_json=cfg)
    box.branch("feat/api", {"apps/api/a.txt": "a\n"})
    r = box.gate("--no-publish")
    steps = {s["name"]: s["outcome"] for s in box.result()["steps"]}
    t.eq("env: the variable reaches the step that declares it, and only that step",
         (r.code, steps["unit"], steps["typecheck"], steps["lint"]), (1, "fail", "pass", "pass"))

    for bad in ({"A": 1}, ["A"], {"": "x"}):
        cfg = Box.gate_json()
        cfg["steps"][0]["env"] = bad
        box = Box(shared, gate_json=cfg)
        box.branch("feat/api", {"apps/api/a.txt": "a\n"})
        r = box.gate("--no-publish")
        t.eq("env: %r is a configuration error" % (bad,), r.code, 2)
        t.has("env: ... that names the step", r.err, "env")


def sc_widening(t: T, shared: Path) -> None:
    box = Box(shared)
    box.branch("feat/lock", {"pnpm-lock.yaml": "lock\nl1\nchanged\n"})
    r = box.gate("--no-publish")
    t.eq("lockfile change: exit 0", r.code, 0)
    log = box.ran()
    t.eq("lockfile change: run_full used for scoped steps",
         [x for x in log if x[0] in ("typecheck", "lint", "unit")],
         [["typecheck", "FULL"], ["lint", "FULL"], ["unit", "FULL"]])
    t.check("lockfile change: e2e runs when widened", any(x[0] == "e2e" for x in log))
    t.eq("lockfile change: result.widened", box.result()["widened"], True)

    box.branch("feat/nested", {"apps/web/package.json": "{}\n"})
    box.clear_log()
    box.gate("--no-publish")
    t.eq("a package's own package.json does not widen", box.result()["widened"], False)
    t.eq("... and the package is the changed set", box.ran()[0], ["typecheck", "apps/web"])

    box.branch("feat/ci", {".github/workflows/ci.yml": "name: x\n"})
    box.clear_log()
    box.gate("--no-publish")
    t.eq("workflow change widens (directory prefix)", box.result()["widened"], True)

    box.branch("feat/full", {"docs/f.txt": "f\n"})
    box.clear_log()
    box.gate("--no-publish", "--full")
    t.eq("--full widens", box.result()["widened"], True)
    t.eq("--full runs run_full", [x for x in box.ran() if x[0] == "typecheck"], [["typecheck", "FULL"]])


def sc_only_skip(t: T, shared: Path) -> None:
    box = Box(shared)
    box.branch("feat/os", {"apps/web/a.txt": "a\n"})
    r = box.gate("--only", "guards")
    t.eq("--only: exit 0", r.code, 0)
    t.eq("--only: just that step ran", [x[0] for x in box.ran()], ["guards"])
    t.eq("--only: setup still runs first", [x[0] for x in box.ran(True)], ["setup", "guards"])
    res = box.result()
    t.eq("--only: result marks partial", res["partial"], True)
    t.eq("--only: unselected steps are skip", {s["name"]: s["outcome"] for s in res["steps"]}["unit"], "skip")
    t.eq("--only: a partial result is never published", box.remote_ref("refs/gate-results/feat/os"), None)
    t.has("--only: says why", r.out, "partial")

    box.clear_log()
    r = box.gate("--no-publish", "--skip", "e2e,lint")
    t.eq("--skip: the rest ran", [x[0] for x in box.ran()], ["typecheck", "unit", "guards", "secret-scan"])
    t.eq("--skip: exit 0", r.code, 0)

    r = box.gate("--no-publish", "--only", "nonsense")
    t.eq("--only with an unknown step: exit 2", r.code, 2)
    t.has("--only with an unknown step: names it", r.err, "nonsense")
    r = box.gate("--no-publish", "--skip", "nonsense")
    t.eq("--skip with an unknown step: exit 2", r.code, 2)

    box.branch("feat/none", {"docs/x.txt": "x\n"})
    box.clear_log()
    r = box.gate("--no-publish", "--only", "unit")
    t.eq("nothing ran: exit 1, the gate cannot decide", r.code, 1)
    t.eq("nothing ran: pass is false", box.result()["pass"], False)

    box.branch("feat/full-run", {"apps/web/b.txt": "b\n"})
    box.gate()
    t.check("a full run is published",
            box.remote_ref("refs/gate-results/feat/full-run") is not None)


def sc_failures(t: T, shared: Path) -> None:
    box = Box(shared)
    box.branch("feat/fail", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-publish", "--keep-going", env={"GATE_TEST_FAIL": "lint"})
    t.eq("a failing step: exit 1", r.code, 1)
    t.eq("a failing step: later steps still ran with --keep-going",
         [x[0] for x in box.ran()], ["typecheck", "lint", "unit", "guards", "secret-scan", "e2e"])
    res = box.result()
    outcomes = {s["name"]: s["outcome"] for s in res["steps"]}
    t.eq("a failing step: lint is fail", outcomes["lint"], "fail")
    t.eq("a failing step: unit is pass", outcomes["unit"], "pass")
    t.eq("a failing step: pass is false", res["pass"], False)
    t.has("summary shows the failure", r.out, "FAIL")

    box.clear_log()
    r = box.gate("--no-publish", "--fail-fast", env={"GATE_TEST_FAIL": "lint"})
    t.eq("--fail-fast: exit 1", r.code, 1)
    t.eq("--fail-fast: stops after the failing step", [x[0] for x in box.ran()], ["typecheck", "lint"])
    outcomes = {s["name"]: s["outcome"] for s in box.result()["steps"]}
    t.eq("--fail-fast: the rest are skip", [outcomes[n] for n in ("unit", "guards", "secret-scan", "e2e")], ["skip"] * 4)

    box.clear_log()
    box.gate("--no-publish", env={"GATE_TEST_FAIL": "lint"})
    box.clear_log()
    box.gate(env={"GATE_TEST_FAIL": "unit"})
    ref = box.remote_ref("refs/gate-results/feat/fail")
    t.check("a failing result is still published", ref is not None)
    published = json.loads(box.origin_git("show", "refs/gate-results/feat/fail:gate-result.json"))
    t.eq("... and says pass false", published["pass"], False)


def sc_config_errors(t: T, shared: Path) -> None:
    box = Box(shared)
    box.branch("feat/cfg", {"apps/web/a.txt": "a\n"})

    r = box.gate("--no-publish", base_ref="origin/nope")
    t.eq("unknown base ref: exit 2", r.code, 2)
    t.has("unknown base ref: says so", r.err, "not found")

    gate_path = box.work / "scripts/delivery/gate.json"
    good = gate_path.read_text(encoding="utf-8")
    bad = json.loads(good)
    bad["steps"][0]["scope"] = "sometimes"
    gate_path.write_text(json.dumps(bad), encoding="utf-8")
    r = box.gate("--no-publish")
    t.eq("invalid gate.json: exit 2", r.code, 2)
    t.has("invalid gate.json: names the problem", r.err, "scope")
    gate_path.write_text(good, encoding="utf-8")
    t.eq("restored gate.json runs", box.gate("--no-publish").code, 0)

    for bad_minutes in (0, -1, "5", True, 1.5, None):
        bad = json.loads(good)
        bad["timeout_minutes"] = bad_minutes
        gate_path.write_text(json.dumps(bad), encoding="utf-8")
        r = box.gate("--no-publish")
        t.eq("timeout_minutes %r: exit 2" % (bad_minutes,), r.code, 2)
        t.has("timeout_minutes %r: names the key" % (bad_minutes,), r.err, "timeout_minutes")
    bad = json.loads(good)
    bad["steps"][0]["name"] = "setup"
    gate_path.write_text(json.dumps(bad), encoding="utf-8")
    r = box.gate("--no-publish")
    t.eq("a step named setup: exit 2", r.code, 2)
    t.has("a step named setup: says it is reserved", r.err, "reserved")
    gate_path.write_text(good, encoding="utf-8")
    t.eq("--timeout-minutes 0: exit 2", box.gate("--no-publish", "--timeout-minutes", "0").code, 2)
    t.eq("--timeout-minutes -3: exit 2", box.gate("--no-publish", "--timeout-minutes=-3").code, 2)

    box.g("checkout", "-q", "--detach")
    t.eq("detached HEAD, publishing: exit 2", box.gate().code, 2)
    t.eq("detached HEAD, --no-publish: exit 0", box.gate("--no-publish").code, 0)
    box.g("checkout", "-q", "feat/cfg")

    box.g("remote", "set-url", "origin", (box.root / "does-not-exist.git").as_posix())
    box.g("update-ref", "refs/remotes/origin/main", box.main_sha)  # keep the base ref
    r = box.gate()
    t.eq("publish fails: exit 2 even though the steps passed", r.code, 2)
    t.has("publish fails: says how to proceed", r.err, "--no-publish")
    t.eq("publish fails: the local result is still written", box.result()["pass"], True)
    t.eq("--no-publish needs no remote", box.gate("--no-publish").code, 0)


def sc_dirty(t: T, shared: Path) -> None:
    box = Box(shared)
    box.branch("feat/dirty", {"apps/web/a.txt": "a\n"})
    box.write("apps/web/a.txt", "edited\n")
    r = box.gate("--no-publish")
    t.eq("modified tracked file: exit 2", r.code, 2)
    t.has("modified tracked file: says the tree is not clean", r.err, "not clean")
    t.eq("modified tracked file: no step ran", box.ran(), [])
    box.g("checkout", "--", "apps/web/a.txt")

    box.write("apps/web/untracked.txt", "u\n")
    t.eq("untracked file: exit 2", box.gate("--no-publish").code, 2)
    (box.work / "apps/web/untracked.txt").unlink()

    box.write("apps/web/staged.txt", "s\n")
    box.g("add", "apps/web/staged.txt")
    t.eq("staged change: exit 2", box.gate("--no-publish").code, 2)
    box.g("reset", "-q", "--hard")

    t.eq("clean tree (with a .delivery/ directory): exit 0", box.gate("--no-publish").code, 0)


def sc_publish(t: T, shared: Path) -> None:
    box = Box(shared)
    first = box.branch("feat/pub", {"apps/web/p.txt": "p\n"})
    r = box.gate()
    t.eq("publish: exit 0", r.code, 0)
    ref1 = box.remote_ref("refs/gate-results/feat/pub")
    t.check("publish: ref exists on the remote", ref1 is not None)
    t.eq("publish: the result commit is parentless",
         [l for l in box.origin_git("cat-file", "-p", ref1).splitlines() if l.startswith("parent ")], [])
    t.eq("publish: the tree holds only gate-result.json",
         box.origin_git("ls-tree", "-r", "--name-only", ref1), "gate-result.json")
    published = json.loads(box.origin_git("show", ref1 + ":gate-result.json"))
    t.eq("publish: content is the local result", published, box.result())
    t.eq("publish: head is the branch head", published["head"], first)
    t.eq("publish: the branch itself is not pushed", box.remote_ref("refs/heads/feat/pub"), None)
    t.eq("publish: nothing lands in branches or tags",
         box.g("ls-remote", "--heads", "--tags", "origin").count("pub"), 0)

    second = box.commit({"apps/web/q.txt": "q\n"}, "more")
    r = box.gate()
    t.eq("republish after a new commit: exit 0", r.code, 0)
    ref2 = box.remote_ref("refs/gate-results/feat/pub")
    t.check("republish: the ref moved (force-pushed)", ref2 is not None and ref2 != ref1)
    t.eq("republish: no history builds up",
         [l for l in box.origin_git("cat-file", "-p", ref2).splitlines() if l.startswith("parent ")], [])
    t.eq("republish: new head",
         json.loads(box.origin_git("show", ref2 + ":gate-result.json"))["head"], second)
    t.eq("one ref per branch", len(box.g("ls-remote", "origin", "refs/gate-results/*").splitlines()), 1)

    box.branch("feat/pub2", {"apps/web/r.txt": "r\n"})
    box.gate()
    t.eq("two branches, two refs", len(box.g("ls-remote", "origin", "refs/gate-results/*").splitlines()), 2)

    box.branch("feat/nopub", {"apps/web/s.txt": "s\n"})
    box.gate("--no-publish")
    t.eq("--no-publish publishes nothing", box.remote_ref("refs/gate-results/feat/nopub"), None)


def sc_setup(t: T, shared: Path) -> None:
    """The gate installs from the lockfile first; a stale lockfile stops it there."""
    box = Box(shared)
    box.branch("feat/web", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-publish")
    t.eq("setup first: exit 0", r.code, 0)
    t.eq("setup runs before every other step", [x[0] for x in box.ran(True)][:2], ["setup", "typecheck"])
    res = box.result()
    first = res["steps"][0]
    t.eq("result: the first step is setup, passed",
         (first["name"], first["outcome"], first["exit_code"], first["reason"]), ("setup", "pass", 0, None))
    t.has("result: the setup command is recorded", first["command"], "_t.py setup")
    t.eq("result: the setup log", first["log"], ".delivery/logs/setup.log")
    t.eq("result: tool version", res["tool"], "branch_gate.py %d" % dc.TOOL_VERSION)
    t.eq("result: not timed out", res["timed_out"], False)

    # a stale lockfile: the frozen install fails, so nothing else runs
    cfg = Box.gate_json()
    cfg["setup"] = [Box.step_cmd("setup"), '"%s" scripts/delivery/_lock.py' % PY]
    box = Box(shared, gate_json=cfg)
    box.branch("feat/stale", {"pnpm-lock.yaml": "lock\nSTALE\n", "apps/web/a.txt": "a\n"})
    r = box.gate()
    t.eq("stale lockfile: exit 1", r.code, 1)
    t.eq("... the first setup command ran, no step did", (box.ran(True), box.ran()), ([["setup"]], []))
    res = box.result()
    st = {s["name"]: s for s in res["steps"]}
    t.eq("... setup is fail", (st["setup"]["outcome"], st["setup"]["exit_code"]), ("fail", 1))
    t.has("... and says which command failed", st["setup"]["reason"], "_lock.py")
    t.eq("... every other step is skip 'setup failed'",
         {n: (s["outcome"], s["reason"]) for n, s in st.items() if n != "setup"},
         {n: ("skip", "setup failed") for n in st if n != "setup"})
    t.eq("... pass is false", res["pass"], False)
    t.has("... the summary names a stale lockfile", r.out, "stale lockfile")
    t.has("... and the FAIL line names setup", r.out, "FAIL setup:")
    t.has("... the install's error is in the log",
          (box.work / ".delivery/logs/setup.log").read_text(encoding="utf-8"), "ERR_PNPM_OUTDATED_LOCKFILE")
    t.has("... and in the tail after the summary", r.out.split("FAIL setup:", 1)[-1], "ERR_PNPM_OUTDATED_LOCKFILE")
    t.check("... the failing result is still published", box.remote_ref("refs/gate-results/feat/stale") is not None)
    box.push("feat/stale")
    t.eq("... and gate_verify does not trust it", verify(box, "feat/stale").code, 1)

    # --keep-going does not carry on past a failed setup
    box.clear_log()
    r = box.gate("--no-publish", "--keep-going")
    t.eq("--keep-going with a failed setup: still stops, exit 1", (r.code, box.ran()), (1, []))

    # --no-setup: partial, never published
    box = Box(shared)
    box.branch("feat/nosetup", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-setup")
    t.eq("--no-setup: exit 0", r.code, 0)
    t.eq("--no-setup: setup did not run", [x[0] for x in box.ran(True)][:1], ["typecheck"])
    res = box.result()
    t.eq("--no-setup: partial", res["partial"], True)
    t.eq("--no-setup: setup recorded as skip", (res["steps"][0]["name"], res["steps"][0]["outcome"], res["steps"][0]["reason"]),
         ("setup", "skip", "--no-setup"))
    t.eq("--no-setup: never published", box.remote_ref("refs/gate-results/feat/nosetup"), None)
    t.has("--no-setup: says the result is partial", r.out, "partial")
    r = box.gate("--no-setup", env={"GATE_TEST_FAIL": "setup"})
    t.eq("--no-setup: a setup that would fail is not run", r.code, 0)

    # a setup that fails without --no-setup, for contrast
    box.clear_log()
    r = box.gate("--no-publish", env={"GATE_TEST_FAIL": "setup"})
    t.eq("setup failing: exit 1, no step ran", (r.code, box.ran()), (1, []))

    # a gate.json with no setup commands has no setup step
    cfg = Box.gate_json()
    cfg["setup"] = []
    box = Box(shared, gate_json=cfg)
    box.branch("feat/nosetupcmds", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-publish")
    t.eq("no setup commands: exit 0", r.code, 0)
    t.eq("... and no setup step", [s["name"] for s in box.result()["steps"]][:1], ["typecheck"])


def sc_failfast(t: T, shared: Path) -> None:
    """Stop at the first failure by default; --keep-going runs on; --fail-fast is a no-op."""
    box = Box(shared)
    box.branch("feat/ff", {"apps/web/a.txt": "a\n"})
    names = ["typecheck", "lint", "unit", "guards", "secret-scan", "e2e"]

    r = box.gate("--no-publish", env={"GATE_TEST_FAIL": "lint"})
    t.eq("default: exit 1", r.code, 1)
    t.eq("default: stops after the first failing step", [x[0] for x in box.ran()], ["typecheck", "lint"])
    st = {s["name"]: s for s in box.result()["steps"]}
    t.eq("default: later steps are skip 'an earlier step failed'",
         [(st[n]["outcome"], st[n]["reason"]) for n in names[2:]], [("skip", "an earlier step failed")] * 4)
    t.eq("default: no log for a step that never ran", (box.work / ".delivery/logs/unit.log").exists(), False)

    box.clear_log()
    r = box.gate("--no-publish", "--keep-going", env={"GATE_TEST_FAIL": "lint"})
    t.eq("--keep-going: exit 1", r.code, 1)
    t.eq("--keep-going: every step ran", [x[0] for x in box.ran()], names)
    st = {s["name"]: s for s in box.result()["steps"]}
    t.eq("--keep-going: only the failing step failed",
         {n: s["outcome"] for n, s in st.items() if s["outcome"] != "pass"}, {"lint": "fail"})

    box.clear_log()
    r = box.gate("--no-publish", "--fail-fast", env={"GATE_TEST_FAIL": "lint"})
    t.eq("--fail-fast: accepted, same as the default", (r.code, [x[0] for x in box.ran()]), (1, ["typecheck", "lint"]))

    box.clear_log()
    r = box.gate("--no-publish", "--fail-fast", "--keep-going", env={"GATE_TEST_FAIL": "lint"})
    t.eq("--fail-fast with --keep-going: --keep-going wins", [x[0] for x in box.ran()], names)

    # a later failure after earlier passes, and a failure in the last step
    box.clear_log()
    r = box.gate("--no-publish", env={"GATE_TEST_FAIL": "e2e"})
    t.eq("a failure in the last step: everything before it ran", (r.code, [x[0] for x in box.ran()]), (1, names))


def sc_logs(t: T, shared: Path) -> None:
    """Step logs, the streamed output, and the FAIL line with the tail."""
    box = Box(shared)
    box.branch("feat/logs", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-publish", env={"GATE_TEST_FAIL": "lint", "GATE_TEST_NOISE": "lint"})
    t.eq("a failing step: exit 1", r.code, 1)
    logs = box.work / ".delivery/logs"
    t.check("a log per step that ran", all((logs / (n + ".log")).is_file() for n in ("setup", "typecheck", "lint")))
    t.check("no log for a step that did not run", not (logs / "unit.log").exists())
    lint_log = (logs / "lint.log").read_text(encoding="utf-8")
    t.check("the log holds stdout and stderr together",
            "[lint] stdout" in lint_log and "[lint] stderr" in lint_log, lint_log)
    t.has("the log holds the whole output", lint_log, "noise line 001")
    t.check("the output is streamed to the terminal too",
            "[typecheck] stdout" in r.out and "[lint] stdout" in r.out, r.out)
    t.has("... stderr as well", r.out, "[lint] stderr")
    st = {s["name"]: s for s in box.result()["steps"]}
    t.eq("result: the log field is relative to the root", st["lint"]["log"], ".delivery/logs/lint.log")
    t.eq("result: a skipped step has no log field", "log" in st["unit"], False)
    t.eq("result: the exit code is recorded", (st["lint"]["exit_code"], st["lint"]["reason"]), (1, "command failed"))

    m = re.search(r"^FAIL lint: command failed \(exit 1, [\d.]+s\) - log: \.delivery/logs/lint\.log\r?$",
                  r.out, re.M)
    t.check("the FAIL line names the step, reason, exit code, seconds and log", m is not None, r.out[-600:])
    t.check("... printed after the summary table", m is not None and r.out.index("outcome") < m.start())
    after = r.out.split("FAIL lint:", 1)[-1]
    t.eq("... followed by the last 40 lines of the step's output",
         len(re.findall(r"noise line \d+", after)), 40)
    t.check("... which are the last ones", "noise line 100" in after and "noise line 061" in after
            and "noise line 060" not in after)
    t.check("a passing step prints no FAIL line", "FAIL typecheck" not in r.out and "FAIL setup" not in r.out)

    r = box.gate("--no-publish")
    t.eq("a passing run: no FAIL line", (r.code, "FAIL " in r.out.replace("FAILURES", "")), (0, False))
    t.has("... and the logs are rewritten", (logs / "lint.log").read_text(encoding="utf-8"), "[lint] stdout")
    t.check("... not appended", "noise line" not in (logs / "lint.log").read_text(encoding="utf-8"))

    # a step never inherits the caller's stdin (it would hang waiting for input)
    cfg = Box.gate_json()
    for st_ in cfg["steps"]:
        if st_["name"] == "guards":
            st_["run"] = '"%s" scripts/delivery/_stdin.py' % PY
    box3 = Box(shared, gate_json=cfg)
    box3.branch("feat/stdin", {"apps/web/a.txt": "a\n"})
    r = run([PY, "scripts/delivery/branch_gate.py", "--base-ref", "origin/main", "--no-publish", "--only", "guards"],
            cwd=box3.work, input_text="x" * 10)
    t.has("a step's stdin is closed, not inherited", r.out, "stdin bytes 0")

    # a step name that is not a safe file name
    cfg = Box.gate_json()
    cfg["steps"][2]["name"] = "type check/ts"  # "unit": typecheck and lint are required steps now (DL-84/DL-85)
    box2 = Box(shared, gate_json=cfg)
    box2.branch("feat/names", {"apps/web/a.txt": "a\n"})
    r = box2.gate("--no-publish")
    t.eq("an unsafe step name still gets a log", (r.code, (box2.work / ".delivery/logs/type_check_ts.log").is_file()), (0, True))


def sc_timeout(t: T, shared: Path) -> None:
    """The time limit kills the running step's whole tree and stops the gate."""
    cfg = Box.gate_json()
    for s in cfg["steps"]:
        if s["name"] == "lint":  # never finishes on its own, and leaves a child behind
            s["run"] = s["run_full"] = '"%s" scripts/delivery/_slow.py' % PY
    box = Box(shared, gate_json=cfg)
    box.branch("feat/slow", {"apps/web/a.txt": "a\n"})
    started = time.monotonic()
    r = box.gate("--timeout-minutes", "0.2")
    elapsed = time.monotonic() - started
    t.eq("timed out: exit 4", r.code, 4)
    t.check("... stopped near the limit (12 s), not when the child ends (30 s)", elapsed < 27, "%.1f s" % elapsed)
    res = box.result()
    st = {s["name"]: s for s in res["steps"]}
    t.eq("... result: timed_out, not passing", (res["timed_out"], res["pass"]), (True, False))
    t.eq("... the running step is fail 'timed out after 0.2 min'",
         (st["lint"]["outcome"], st["lint"]["reason"]), ("fail", "timed out after 0.2 min"))
    t.eq("... the steps before it passed", (st["setup"]["outcome"], st["typecheck"]["outcome"]), ("pass", "pass"))
    t.eq("... the rest are skip 'gate timed out'",
         [(st[n]["outcome"], st[n]["reason"]) for n in ("unit", "guards", "secret-scan", "e2e")],
         [("skip", "gate timed out")] * 4)
    t.check("... the later steps never ran", not any(x[0] in ("unit", "guards") for x in box.ran()))
    t.has("... says the gate timed out", r.err, "timed out")
    t.has("... the FAIL line names the timeout", r.out, "FAIL lint: timed out after 0.2 min")
    t.has("... the output up to the kill is in the log",
          (box.work / ".delivery/logs/lint.log").read_text(encoding="utf-8"), "slow step started")
    t.check("... the result is published",
            box.remote_ref("refs/gate-results/feat/slow") is not None)
    published = json.loads(box.origin_git("show", "refs/gate-results/feat/slow:gate-result.json"))
    t.eq("... with timed_out true", (published["timed_out"], published["pass"]), (True, False))

    beat = box.work / ".delivery/child.beat"
    before = beat.stat().st_size if beat.exists() else 0
    t.check("the step's child did run", before > 0)
    time.sleep(1.5)
    after = beat.stat().st_size if beat.exists() else 0
    t.eq("... and was killed with the step (its heartbeat stopped)", after, before)

    box.push("feat/slow")
    v = verify(box, "feat/slow")
    t.eq("gate_verify does not trust a timed-out result", v.code, 1)

    # the grace: with the limit already used up, required steps (lint, types) still run
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ctx = dc.Context(root=Path(tmp), cfg={}, base_ref="origin/main", base="b", head="h", files=[],
                         packages=[], changed_dirs=[], affected_dirs=[], widened=False)
        ok = '"%s" -c "print(1)"' % PY
        steps = [{"name": n, "scope": "always", "run": ok} for n in ("typecheck", "lint", "unit")]
        ents, hit = dc.execute_steps(steps, ctx, limit_seconds=1e-9, required_steps=["typecheck", "lint"])
        got = {e["name"]: (e["outcome"], e["reason"]) for e in ents}
        t.eq("grace: required steps still run after the limit is used up",
             (got["typecheck"], got["lint"]), (("pass", None), ("pass", None)))
        t.eq("grace: ... other steps are skipped 'gate timed out'", got["unit"], ("skip", "gate timed out"))
        t.eq("grace: ... and the run is marked timed out", hit, True)
        ents, hit = dc.execute_steps(steps, ctx, limit_seconds=1e-9)
        t.eq("grace: without required steps, everything is skipped",
             sorted({e["outcome"] for e in ents}), ["skip"])

    # a short limit set in gate.json and the flag that overrides it
    box = Box(shared)
    box.branch("feat/lim", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-publish", "--only", "guards")
    t.has("the default limit is 30 min", r.out, "limit   : 30 min")
    box.commit({"scripts/delivery/gate.json": json.dumps({**Box.gate_json(), "timeout_minutes": 7})}, "limit")
    r = box.gate("--no-publish", "--only", "guards")
    t.has("gate.json timeout_minutes is used", r.out, "limit   : 7 min")
    r = box.gate("--no-publish", "--only", "guards", "--timeout-minutes", "3")
    t.has("--timeout-minutes overrides it", r.out, "limit   : 3 min")


# --------------------------------------------------------------------------
# scenarios: gate_verify.py
# --------------------------------------------------------------------------

def verify(box: Box, branch: str, *args: str, base_ref: str = "origin/main") -> R:
    return box.script("gate_verify.py", branch, "--base-ref", base_ref, *args)


def sc_verify(t: T, shared: Path) -> None:
    box = Box(shared)
    box.gated("feat/ok", {"apps/web/ok.txt": "ok\n"})
    box.gated("feat/failing", {"apps/web/f.txt": "f\n"}, fail="unit")
    box.gated("feat/moved", {"apps/web/m.txt": "m\n"})
    box.branch("feat/ungated", {"apps/web/u.txt": "u\n"})
    box.push("feat/ungated")
    box.g("checkout", "-q", "feat/moved")
    box.commit({"apps/web/m2.txt": "m2\n"}, "after the gate")
    box.push("feat/moved")

    # a gate result copied under another branch's name
    box.g("fetch", "-q", "origin", "+refs/gate-results/feat/ok:refs/tmp/ok")
    box.g("push", "-q", "origin", "refs/tmp/ok:refs/gate-results/feat/copy")
    box.g("checkout", "-q", "-B", "feat/copy", "feat/ok")
    box.push("feat/copy")

    # crafted results
    box.g("checkout", "-q", "-B", "feat/partial", "feat/ok")
    box.push("feat/partial")
    good = json.loads(box.origin_git("show", "refs/gate-results/feat/ok:gate-result.json"))
    box.publish_raw("feat/partial", json.dumps({**good, "branch": "feat/partial", "partial": True}))
    box.g("checkout", "-q", "-B", "feat/garbage", "feat/ok")
    box.push("feat/garbage")
    box.publish_raw("feat/garbage", "not json at all")
    box.g("checkout", "-q", "-B", "feat/timedout", "feat/ok")
    box.push("feat/timedout")
    box.publish_raw("feat/timedout", json.dumps({**good, "branch": "feat/timedout", "timed_out": True}))
    box.g("checkout", "-q", "-B", "feat/setupfail", "feat/ok")
    box.push("feat/setupfail")
    box.publish_raw("feat/setupfail", json.dumps({
        **good, "branch": "feat/setupfail",
        "steps": [{"name": "setup", "outcome": "fail", "seconds": 1.0, "command": "x", "reason": "command failed",
                   "exit_code": 1}] + good["steps"][1:]}))
    box.g("checkout", "-q", "-B", "feat/oldschema", "feat/ok")
    box.push("feat/oldschema")
    box.publish_raw("feat/oldschema", json.dumps({**good, "branch": "feat/oldschema", "schema": 99}))

    r = verify(box, "feat/ok")
    t.eq("fresh passing result: trusted, exit 0", r.code, 0)
    t.has("fresh passing result: says TRUSTED", r.out, "TRUSTED")
    j = json.loads(verify(box, "feat/ok", "--json").out)
    t.eq("--json: trusted", (j["trusted"], j["exit"], j["reasons"]), (True, 0, []))
    t.eq("--json: shas", (j["branch_head"], j["result_head"]),
         (box.g("rev-parse", "origin/feat/ok"),) * 2)

    r = verify(box, "feat/moved")
    t.eq("stale head (branch moved after the gate): exit 1", r.code, 1)
    t.has("stale head: says so", r.out, "stale head")

    r = verify(box, "feat/ungated")
    t.eq("no result published: exit 2", r.code, 2)
    t.has("no result: says what to run", r.out, "branch_gate.py")
    r = verify(box, "feat/not-on-remote")
    t.eq("branch not on the remote: exit 2", r.code, 2)

    r = verify(box, "feat/failing")
    t.eq("failing result: exit 1", r.code, 1)
    t.has("failing result: says failing and which step", r.out, "unit")

    r = verify(box, "feat/copy")
    t.eq("a result copied from another branch: exit 1", r.code, 1)
    t.has("... because it is for another branch", r.out, "feat/ok")

    r = verify(box, "feat/partial")
    t.eq("partial result: exit 1", r.code, 1)
    t.has("partial result: says partial", r.out, "partial")
    r = verify(box, "feat/timedout")
    t.eq("a timed-out result that claims pass: exit 1", r.code, 1)
    t.has("... says it timed out", r.out, "timed out")
    r = verify(box, "feat/setupfail")
    t.eq("a result whose setup failed but claims pass: exit 1", r.code, 1)
    t.has("... says setup did not pass", r.out, "setup did not pass")
    t.eq("garbage result: exit 1", verify(box, "feat/garbage").code, 1)
    t.eq("unknown schema: exit 1", verify(box, "feat/oldschema").code, 1)

    # default --base-ref and --remote
    r = box.script("gate_verify.py", "feat/ok", "--remote", "origin")
    t.eq("default base ref is <remote>/<default_branch>", r.code, 0)

    # now main moves on: every earlier result has a stale base
    box.g("checkout", "-q", "main")
    box.commit({"apps/api/main2.txt": "m\n"}, "main moves")  # code, so not an inert move (DL1)
    box.g("push", "-q", "origin", "main")
    r = verify(box, "feat/ok")
    t.eq("stale base (the target moved): exit 1", r.code, 1)
    t.has("stale base: says so", r.out, "stale base")
    r = verify(box, "feat/ok", "--allow-older-base")
    t.eq("--allow-older-base: an ancestor base is accepted", r.code, 0)
    t.has("--allow-older-base: says so", r.out, "older base")
    r = verify(box, "feat/failing", "--allow-older-base")
    t.eq("--allow-older-base does not excuse a failing result", r.code, 1)
    r = verify(box, "feat/moved", "--allow-older-base")
    t.eq("--allow-older-base does not excuse a stale head", r.code, 1)

    # the target is rewound: the result's base is no longer an ancestor of it
    box.g("push", "-q", "--force", "origin", box.main_sha + "~1:refs/heads/main")
    r = verify(box, "feat/ok", "--allow-older-base")
    t.eq("--allow-older-base needs an ancestor: exit 1", r.code, 1)
    t.has("... and explains", r.out, "not an ancestor")


# --------------------------------------------------------------------------
# scenarios: fast_guards.py and the pre-push hook
# --------------------------------------------------------------------------

def sc_fast_guards(t: T, shared: Path) -> None:
    box = Box(shared)
    head = box.branch("feat/fg", {"apps/web/a.txt": "a\n"})
    r = box.script("fast_guards.py", "--base-ref", "origin/main")
    t.eq("exit 0 when the guards pass", r.code, 0)
    t.eq("runs only the pre_push steps", [x[0] for x in box.ran()], ["guards", "secret-scan"])
    t.eq("{base} is the merge base", box.ran()[1], ["secret-scan", box.main_sha])
    t.eq("never writes a result", (box.work / dc.GATE_RESULT_PATH).exists(), False)
    t.eq("never publishes", box.g("ls-remote", "origin", "refs/gate-results/*"), "")

    box.clear_log()
    r = box.script("fast_guards.py", "--base-ref", "origin/main", env={"GATE_TEST_FAIL": "guards"})
    t.eq("a failing guard: exit 1", r.code, 1)
    t.eq("a failing guard: the scan still ran", [x[0] for x in box.ran()], ["guards", "secret-scan"])

    box.commit({"apps/web/b.txt": "b\n"}, "second")
    box.clear_log()
    r = box.script("fast_guards.py", "--base-ref", head)
    t.eq("--base-ref accepts a commit", (r.code, box.ran()[1]), (0, ["secret-scan", head]))

    r = box.script("fast_guards.py", "--base-ref", "origin/nope")
    t.eq("unknown base ref: exit 2", r.code, 2)

    gate_path = box.work / "scripts/delivery/gate.json"
    cfg = json.loads(gate_path.read_text(encoding="utf-8"))
    for s in cfg["steps"]:
        s.pop("pre_push", None)
    gate_path.write_text(json.dumps(cfg), encoding="utf-8")
    r = box.script("fast_guards.py", "--base-ref", "origin/main")
    t.eq("no pre_push step configured: exit 2", r.code, 2)


def sc_required_steps(t: T, shared: Path) -> None:
    """Lint and types come before the test steps and cannot be skipped (DL-84)."""
    box = Box(shared)
    head = box.branch("feat/req", {"apps/web/a.txt": "a\n"})
    gate_path = box.work / "scripts/delivery/gate.json"
    good = gate_path.read_text(encoding="utf-8")
    cfg = json.loads(good)
    r = box.gate("--no-publish")
    t.eq("default gate passes", r.code, 0)
    t.eq("... and records the default required steps",
         box.result()["required_steps"], ["typecheck", "lint"])

    bad = json.loads(good)
    names = [s["name"] for s in bad["steps"]]
    bad["steps"].insert(names.index("lint"), bad["steps"].pop(names.index("unit")))
    box.commit({"scripts/delivery/gate.json": json.dumps(bad)}, "cfg")
    r = box.gate("--no-publish")
    t.eq("a test step before lint: exit 2", r.code, 2)
    t.has("... says which step and why", r.err, "unit")
    t.has("... names the required steps", r.err, "required step")

    bad = json.loads(good)
    bad["required_steps"] = ["nope"]
    box.commit({"scripts/delivery/gate.json": json.dumps(bad)}, "cfg")
    t.eq("an unknown required step: exit 2", box.gate("--no-publish").code, 2)

    bad = json.loads(good)
    bad["required_steps"] = []
    bad["steps"].insert(0, bad["steps"].pop([s["name"] for s in bad["steps"]].index("unit")))
    box.commit({"scripts/delivery/gate.json": json.dumps(bad)}, "cfg")
    t.eq("required_steps [] turns the order check off", box.gate("--no-publish").code, 0)

    # gate_verify refuses a result where lint or types did not run
    box = Box(shared)
    box.gated("feat/ok", {"apps/web/ok.txt": "ok\n"})
    good_res = json.loads(box.origin_git("show", "refs/gate-results/feat/ok:gate-result.json"))
    t.eq("a normal result is trusted", verify(box, "feat/ok").code, 0)
    cases = {
        "lint-notsel": ("lint", {"outcome": "skip", "reason": "not selected", "command": None}),
        "types-timeout": ("typecheck", {"outcome": "skip", "reason": "gate timed out", "command": None}),
        "lint-nopkg": ("lint", {"outcome": "skip", "reason": "no package changed", "command": None}),
    }
    for branch, (step, change) in cases.items():
        box.g("checkout", "-q", "-B", "feat/" + branch, "feat/ok")
        box.push("feat/" + branch)
        steps = [{**x, **change} if x["name"] == step else x for x in good_res["steps"]]
        box.publish_raw("feat/" + branch, json.dumps({**good_res, "branch": "feat/" + branch, "steps": steps}))
    box.g("checkout", "-q", "-B", "feat/lint-gone", "feat/ok")
    box.push("feat/lint-gone")
    box.publish_raw("feat/lint-gone", json.dumps({**good_res, "branch": "feat/lint-gone",
                    "steps": [x for x in good_res["steps"] if x["name"] != "lint"]}))
    box.g("checkout", "-q", "-B", "feat/old", "feat/ok")
    box.push("feat/old")
    old = {k: v for k, v in good_res.items() if k != "required_steps"}
    box.publish_raw("feat/old", json.dumps({**old, "branch": "feat/old",
                    "steps": [x for x in good_res["steps"] if x["name"] != "typecheck"]}))
    r = verify(box, "feat/lint-notsel")
    t.eq("lint skipped as 'not selected': refused", r.code, 1)
    t.has("... says the required step did not run", r.out, "required step 'lint' did not run")
    t.eq("typecheck skipped for the time limit: refused", verify(box, "feat/types-timeout").code, 1)
    t.eq("lint skipped because no package changed: trusted", verify(box, "feat/lint-nopkg").code, 0)
    r = verify(box, "feat/lint-gone")
    t.eq("lint missing from the result: refused", r.code, 1)
    t.has("... says it is not in the result", r.out, "not in the result")
    t.eq("an older result without required_steps: a missing typecheck is not required of it",
         verify(box, "feat/old").code, 0)

    # the shipped gate.json of every track: order, and lint/types in the pre-push hook
    tooling = shared.parent
    for track in ("ts", "go", "rust", "dotnet"):
        c = dc.load_gate(tooling / track)
        order = [x["name"] for x in c["steps"]]
        last_req = max(order.index(n) for n in c["required_steps"])
        t.check("%s: typecheck is a required step" % track, "typecheck" in c["required_steps"])
        t.check("%s: guards come before typecheck" % track, order.index("guards") < order.index("typecheck"))
        t.check("%s: unit comes after the required steps" % track, order.index("unit") > last_req)
        t.check("%s: required steps also run in pre-push" % track,
                all(x["pre_push"] for x in c["steps"] if x["name"] in c["required_steps"]))


def e2e_gate_json(with_map: bool = True, placeholder: bool = True) -> dict:
    cfg = Box.gate_json()
    for s in cfg["steps"]:
        if s["name"] == "e2e":
            s["run"] = Box.step_cmd("e2e", "{e2e_specs}" if placeholder else "")
            s["run_full"] = Box.step_cmd("e2e", "FULL")
    if with_map:
        cfg["e2e_map"] = {
            "specs": [
                {"spec": "e2e/checkout.spec.ts", "paths": ["apps/web/checkout/"]},
                {"spec": "e2e/ui.spec.ts", "paths": ["packages/ui/"]},
                {"spec": "e2e/core.spec.ts", "paths": ["packages/core/"]},
            ],
            "full_on": ["playwright.config.txt"],
        }
    return cfg


def sc_e2e_map(t: T, shared: Path) -> None:
    """U1: the e2e step runs only the specs the changed files map to."""
    box = Box(shared, gate_json=e2e_gate_json())

    def e2e(files: dict, *args: str):
        box.branch("feat/e", files)
        box.clear_log()
        r = box.gate("--no-publish", *args)
        entry = {s["name"]: s for s in box.result()["steps"]}["e2e"]
        return r, [x for x in box.ran() if x[0] == "e2e"], entry

    r, ran, entry = e2e({"apps/web/checkout/a.txt": "a\n"})
    t.eq("a mapped change runs only its spec", (r.code, ran), (0, [["e2e", "e2e/checkout.spec.ts"]]))
    t.eq("... the result says affected, and which", (entry.get("selection"), entry.get("specs")),
         ("affected", ["e2e/checkout.spec.ts"]))
    t.check("... the recorded command has the specs filled in", "e2e/checkout.spec.ts" in entry["command"]
            and "{" not in entry["command"], entry["command"])

    r, ran, entry = e2e({"apps/web/checkout/a.txt": "a\n", "packages/ui/b.txt": "b\n"})
    t.eq("two mapped changes run both specs, sorted", ran, [["e2e", "e2e/checkout.spec.ts", "e2e/ui.spec.ts"]])
    t.eq("... recorded", entry.get("specs"), ["e2e/checkout.spec.ts", "e2e/ui.spec.ts"])

    r, ran, entry = e2e({"apps/web/checkout/a.txt": "a\n", "packages/core/c.txt": "c\n"})
    t.eq("a non-UI file under a spec's paths adds that spec", entry.get("specs"),
         ["e2e/checkout.spec.ts", "e2e/core.spec.ts"])

    r, ran, entry = e2e({"apps/web/checkout/a.txt": "a\n", "apps/web/other.txt": "o\n"})
    t.eq("an unmapped UI file: the whole suite", (r.code, ran), (0, [["e2e", "FULL"]]))
    t.eq("... the result says full, no specs", (entry.get("selection"), entry.get("specs")), ("full", []))

    r, ran, entry = e2e({"apps/web/checkout/a.txt": "a\n", "playwright.config.txt": "c\n"})
    t.eq("a full_on file: the whole suite", ran, [["e2e", "FULL"]])
    t.eq("... the result says full", (entry.get("selection"), entry.get("specs")), ("full", []))

    r, ran, entry = e2e({"apps/web/checkout/a.txt": "a\n", "pnpm-lock.yaml": "lock\nl1\nchanged\n"})
    t.eq("a widened gate: the whole suite", ran, [["e2e", "FULL"]])
    t.eq("... the result says full", (entry.get("selection"), entry.get("specs")), ("full", []))

    r, ran, entry = e2e({"apps/web/checkout/a.txt": "a\n"}, "--full")
    t.eq("--full: the whole suite", ran, [["e2e", "FULL"]])

    box.branch("feat/api", {"apps/api/a.txt": "a\n"})
    box.clear_log()
    box.gate("--no-publish")
    entry = {s["name"]: s for s in box.result()["steps"]}["e2e"]
    t.eq("no UI change: e2e is skipped, with no selection fields",
         (entry["outcome"], "selection" in entry, "specs" in entry), ("skip", False, False))

    # no map: the placeholder is empty and the step runs as it always did
    nomap = Box(shared, gate_json=e2e_gate_json(with_map=False))
    nomap.branch("feat/e", {"apps/web/checkout/a.txt": "a\n"})
    r = nomap.gate("--no-publish")
    entry = {s["name"]: s for s in nomap.result()["steps"]}["e2e"]
    t.eq("no e2e_map: the placeholder is empty", (r.code, [x for x in nomap.ran() if x[0] == "e2e"]),
         (0, [["e2e"]]))
    t.eq("... and the selection is full", (entry.get("selection"), entry.get("specs")), ("full", []))
    plain = Box(shared)
    plain.branch("feat/e", {"apps/web/checkout/a.txt": "a\n"})
    plain.gate("--no-publish")
    entry = {s["name"]: s for s in plain.result()["steps"]}["e2e"]
    t.eq("a step without the placeholder: unchanged, no selection fields",
         (entry["outcome"], "selection" in entry), ("pass", False))

    for bad in ("x", {"specs": "x"}, {"specs": [{"spec": "a"}]}, {"specs": [{"spec": "", "paths": ["a/"]}]},
                {"specs": [{"spec": "a", "paths": []}]}, {"specs": [], "full_on": "x"}):
        cfg = e2e_gate_json()
        cfg["e2e_map"] = bad
        b = Box(shared, gate_json=cfg)
        b.branch("feat/e", {"apps/web/checkout/a.txt": "a\n"})
        t.eq("e2e_map %r is a configuration error" % (bad,), b.gate("--no-publish").code, 2)


def sc_e2e_agent(t: T, shared: Path) -> None:
    """DS35 (DL-86..DL-88): the result records the e2e specs; verify and the push hook hold a UI branch to them."""
    box = Box(shared, gate_json=e2e_gate_json())

    def rec() -> dict:
        return box.result()["e2e"]

    # 1. a mapped UI change: required, ran, passed, the specs named
    box.branch("feat/ui", {"apps/web/checkout/a.txt": "a\n"})
    box.clear_log()
    r = box.gate()
    t.eq("a UI change: the result has an e2e record",
         (r.code, rec()["required"], rec()["outcome"], rec()["selection"], rec()["specs"]),
         (0, True, "pass", "affected", ["e2e/checkout.spec.ts"]))
    t.check("... and says ui_changed", box.result()["ui_changed"] is True)
    box.push("feat/ui")
    v = box.script("gate_verify.py", "feat/ui", "--json")
    t.eq("verify trusts a UI branch with a passing e2e record", v.code, 0)

    # 2. a record that is missing or failing refuses the branch
    good = json.loads(box.origin_git("show", "refs/gate-results/feat/ui:gate-result.json"))
    no_rec = {k: val for k, val in good.items() if k not in ("e2e", "ui_changed")}
    box.publish_raw("feat/ui", json.dumps(no_rec))
    v = box.script("gate_verify.py", "feat/ui")
    t.eq("verify refuses a UI branch without the e2e record", v.code, 1)
    t.has("... in plain words, with the command", v.out, "no e2e record")
    t.has("... naming the command", v.out, "branch_gate.py --e2e-only")
    box.publish_raw("feat/ui", json.dumps({**good, "e2e": {**good["e2e"], "outcome": "skip"}}))
    v = box.script("gate_verify.py", "feat/ui")
    t.eq("verify refuses a UI branch whose e2e did not pass", v.code, 1)
    box.publish_raw("feat/ui", json.dumps(good))
    t.eq("... the real record is trusted again", box.script("gate_verify.py", "feat/ui").code, 0)

    # 3. a branch with no UI change needs no record
    box.branch("feat/api", {"apps/api/a.txt": "a\n"})
    box.gate()
    t.eq("no UI change: e2e not required", (rec()["required"], rec()["outcome"]), (False, "skip"))
    box.push("feat/api")
    box.publish_raw("feat/api", json.dumps({k: val for k, val in box.result().items() if k not in ("e2e", "ui_changed")}))
    t.eq("... and verify needs no record", box.script("gate_verify.py", "feat/api").code, 0)

    # 4. --e2e-only: only the e2e step, partial, published; the CI-gate check accepts it
    box.branch("feat/ci", {"apps/web/checkout/b.txt": "b\n"})
    box.push("feat/ci")
    box.clear_log()
    r = box.gate("--e2e-only")
    t.eq("--e2e-only runs only the e2e step", (r.code, [x[0] for x in box.ran()]), (0, ["e2e"]))
    t.check("... the result is partial and e2e_only", box.result()["partial"] and box.result()["e2e_only"])
    t.check("... and is published", box.remote_ref("refs/gate-results/feat/ci") is not None)
    t.eq("verify still refuses a partial result", box.script("gate_verify.py", "feat/ci").code, 1)
    check = (
        "import sys; sys.path.insert(0, 'scripts/delivery'); import gate_verify as g; "
        "print(g.e2e_gate_check('feat/ci', 'origin/main'))"
    )
    t.eq("the CI-gate check accepts the e2e-only record", run([PY, "-c", check], cwd=box.work).out.strip(), "[]")
    box.branch("feat/ci2", {"apps/web/checkout/c.txt": "c\n"})
    box.push("feat/ci2")
    out = run([PY, "-c", check.replace("feat/ci", "feat/ci2")], cwd=box.work).out
    t.has("the CI-gate check holds a UI branch with no record", out, "no e2e record published")
    box.gate("--e2e-only", "--no-publish")
    box.g("checkout", "-q", "feat/api")
    box.clear_log()
    r = box.gate("--e2e-only")
    t.eq("--e2e-only with no UI change: nothing to run, exit 0", (r.code, box.ran()), (0, []))

    # 5. a changed spec file is run, alone, and recorded
    box.branch("feat/spec", {"e2e/checkout.spec.ts": "test\n"})
    box.clear_log()
    r = box.gate("--e2e-only", "--no-publish")
    t.eq("a spec-only change runs that spec", (r.code, [x for x in box.ran() if x[0] == "e2e"]),
         (0, [["e2e", "e2e/checkout.spec.ts"]]))
    t.eq("... recorded with changed_specs", (rec()["specs"], rec()["changed_specs"]),
         (["e2e/checkout.spec.ts"], ["e2e/checkout.spec.ts"]))

    # 6. the push hook: changed specs need a run for exactly that head
    def hook(sha: str, base: str = "origin/main") -> R:
        return box.script("e2e_push_check.py", "--commit", sha, "--base-ref", base)

    head = box.g("rev-parse", "HEAD")
    t.eq("the push check allows a spec change that was run", hook(head).code, 0)
    head2 = box.commit({"e2e/checkout.spec.ts": "test2\n"}, "blind e2e fix")
    r = hook(head2)
    t.eq("... and refuses the next, unrun fix", r.code, 1)
    t.has("... naming the spec", r.err, "e2e/checkout.spec.ts")
    t.has("... and the command", r.err, "branch_gate.py --e2e-only")
    t.eq("a range with no spec change is not held", hook(head2, base=head2).code, 0)
    box.g("checkout", "-q", "feat/ui")
    t.eq("a UI-only commit is not held by the push check", hook(box.g("rev-parse", "HEAD")).code, 0)
    box.g("checkout", "-q", "feat/spec")
    box.gate("--e2e-only", "--no-publish", env={"GATE_TEST_FAIL": "e2e"})
    t.eq("a failing e2e run does not allow the push", hook(box.g("rev-parse", "HEAD")).code, 1)
    box.gate("--e2e-only", "--no-publish")
    t.eq("... a passing one does", hook(box.g("rev-parse", "HEAD")).code, 0)
    # the real hook runs the check
    box.g("checkout", "-q", "feat/spec")
    box.commit({"e2e/checkout.spec.ts": "test3\n"}, "blind again")
    box.g("config", "core.hooksPath", ".githooks")
    p = run(["git", "push", "origin", "feat/spec"], cwd=box.work)
    t.check("the pre-push hook refuses an unrun e2e fix", p.code != 0 and "e2e-push: blocked" in p.err, p.text)


def advanced_box(shared: Path, gate_json: dict | None = None) -> tuple[Box, str]:
    """A box whose origin/main is behind the remote: another clone added a commit
    to main (apps/api) and pushed feat/x, cut from that commit. The box has the
    commits of feat/x (fetched by name) but its origin/main is stale. Returns the
    box, on feat/x, and the new main sha."""
    box = Box(shared, gate_json=gate_json)
    other = box.root / "other"
    run(["git", "clone", "-q", box.origin.as_posix(), other])
    box.g("checkout", "-q", "main", cwd=other)
    new_main = commit_in(box, other, {"apps/api/new.txt": "n\n"}, "main moves")
    box.g("push", "-q", "origin", "main", cwd=other)
    box.g("checkout", "-q", "-b", "feat/x", cwd=other)
    commit_in(box, other, {"apps/web/x.txt": "x\n"}, "work on x")
    box.g("push", "-q", "origin", "feat/x", cwd=other)
    box.g("fetch", "-q", "origin", "feat/x")
    box.g("checkout", "-q", "-B", "feat/x", "FETCH_HEAD")
    return box, new_main


def commit_in(box: Box, cwd: Path, files: dict, msg: str) -> str:
    """Commit files in another clone of the box's origin."""
    for rel, text in files.items():
        p = cwd / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    box.g("add", "-A", cwd=cwd)
    box.g("commit", "-q", "-m", msg, cwd=cwd)
    return box.g("rev-parse", "HEAD", cwd=cwd)


def sc_base_fetch(t: T, shared: Path) -> None:
    """U2: the gate and fast_guards fetch the base first; offline they warn and go on."""
    box, new_main = advanced_box(shared)
    t.check("setup: origin/main is behind", box.g("rev-parse", "origin/main") != new_main)
    r = box.gate("--no-publish")
    res = box.result()
    t.eq("gate: exit 0", r.code, 0)
    t.eq("gate: the base is the fetched head", res["base"], new_main)
    t.eq("gate: so only the branch's own package changed", res["changed_dirs"], ["apps/web"])
    t.eq("gate: base_fetched is true", res["base_fetched"], True)
    t.eq("gate: origin/main moved", box.g("rev-parse", "origin/main"), new_main)
    t.check("gate: no warning when the fetch worked", "not fetched" not in r.text, r.text)

    box, new_main = advanced_box(shared)
    r = box.script("fast_guards.py", "--base-ref", "origin/main")
    t.eq("fast_guards: exit 0", r.code, 0)
    t.eq("fast_guards: {base} is the fetched head", box.ran()[1], ["secret-scan", new_main])

    # offline: the remote cannot be reached
    box, new_main = advanced_box(shared)
    box.g("remote", "set-url", "origin", (box.root / "gone.git").as_posix())
    stale = box.g("rev-parse", "origin/main")
    r = box.gate("--no-publish")
    res = box.result()
    t.eq("offline gate: still runs", r.code, 0)
    t.has("offline gate: warns", r.err, "base not fetched")
    t.has("offline gate: says the local ref is used", r.err, "using the local ref")
    t.eq("offline gate: base_fetched is false", res["base_fetched"], False)
    t.eq("offline gate: the stale local ref is the base", res["base"], stale)
    box.clear_log()
    r = box.script("fast_guards.py", "--base-ref", "origin/main")
    t.eq("offline fast_guards: still runs", r.code, 0)
    t.has("offline fast_guards: warns", r.err, "base not fetched")

    # nothing to fetch: a local branch, a commit
    box = Box(shared)
    box.branch("feat/l", {"apps/web/a.txt": "a\n"})
    r = box.gate("--no-publish", base_ref="main")
    t.eq("a local base branch: no fetch, no warning",
         (r.code, box.result()["base_fetched"], "not fetched" in r.text), (0, False, False))
    r = box.gate("--no-publish", base_ref=box.main_sha)
    t.eq("a commit as base: no fetch, no warning",
         (r.code, box.result()["base_fetched"], "not fetched" in r.text), (0, False, False))


def fork_box(shared: Path) -> Box:
    """origin has main and integ (one commit ahead of main); the box has both."""
    box = Box(shared)
    box.branch("integ", {"apps/api/i.txt": "i\n"})
    box.push("integ")
    return box


def fork_base(box: Box, *args: str) -> tuple[R, str | None]:
    r = box.script("fast_guards.py", "--base-ref", "auto", *args)
    m = re.search(r"^base: (\S+) \(fork point\)\r?$", r.out, re.M)
    return r, m.group(1) if m else None


def sc_fork_point(t: T, shared: Path) -> None:
    """U3: --base-ref auto picks the remote branch the commit was cut from."""
    box = fork_box(shared)
    integ = box.g("rev-parse", "integ")
    box.g("remote", "set-head", "origin", "integ")  # origin/HEAD -> integ: it must never be picked
    box.branch("feat/f", {"apps/web/f.txt": "f\n"}, frm="integ")
    box.clear_log()
    r, base = fork_base(box)
    t.eq("a branch cut from an integration branch picks it", (r.code, base), (0, "origin/integ"))
    t.eq("... and {base} is that branch's head", box.ran()[1], ["secret-scan", integ])
    box.push("feat/f")
    r, base = fork_base(box)
    t.eq("the pushed branch itself is never the base (checked-out name)", base, "origin/integ")
    box.g("checkout", "-q", "integ")
    r, base = fork_base(box, "--commit", "feat/f", "--branch", "feat/f")
    t.eq("... nor with --branch, for a commit that is not checked out", (r.code, base), (0, "origin/integ"))

    box.g("remote", "set-head", "origin", "main")
    box.branch("feat/m", {"apps/web/m.txt": "m\n"}, frm="main")
    box.clear_log()
    r, base = fork_base(box)
    t.eq("a branch cut from main picks main", (r.code, base), (0, "origin/main"))
    t.eq("... {base} is main's head", box.ran()[1], ["secret-scan", box.main_sha])

    # ties go to the default branch, then to name order
    box = Box(shared)
    box.g("push", "-q", "origin", "main:refs/heads/aaa")
    box.g("fetch", "-q", "origin")
    box.branch("feat/t", {"apps/web/t.txt": "t\n"}, frm="main")
    r, base = fork_base(box)
    t.eq("a tie with the default branch: the default branch", base, "origin/main")

    box = Box(shared)
    box.branch("b-int", {"apps/api/b.txt": "b\n"})
    box.push("b-int")
    box.g("push", "-q", "origin", "b-int:refs/heads/a-int")
    box.g("fetch", "-q", "origin")
    box.branch("feat/t", {"apps/web/t.txt": "t\n"}, frm="b-int")
    r, base = fork_base(box)
    t.eq("a tie between other branches: name order", base, "origin/a-int")

    # no candidate: the default branch
    box = Box(shared)
    box.branch("feat/n", {"apps/web/n.txt": "n\n"})
    r, base = fork_base(box, "--branch", "main")
    t.eq("no candidate: the default branch", (r.code, base), (0, "origin/main"))

    # an unrelated branch is skipped, not an error
    box = Box(shared)
    box.g("checkout", "-q", "--orphan", "island")
    box.g("rm", "-rfq", ".")
    box.commit({"island.txt": "i\n"}, "island")
    box.g("push", "-q", "origin", "island")
    box.branch("feat/u", {"apps/web/u.txt": "u\n"}, frm="main")
    r, base = fork_base(box)
    t.eq("a branch with no common ancestor is skipped", (r.code, base), (0, "origin/main"))


def push_leftovers(box: Box) -> list:
    """What a finished fast_guards.py --commit run must not leave: directories under
    .delivery/push-check/, and worktrees registered with the repository."""
    d = box.work / ".delivery/push-check"
    names = sorted(p.name for p in d.iterdir()) if d.is_dir() else []
    listed = [x for x in box.g("worktree", "list").splitlines() if x.strip()]
    return names + ["registered worktree"] * (len(listed) - 1)


def sc_push_check(t: T, shared: Path) -> None:
    """fast_guards.py --commit: the guards judge a commit that is not checked out."""
    box = Box(shared)
    (box.work / ".git/info/exclude").write_text("node_modules/\n", encoding="utf-8")
    clean = box.branch("feat/clean", {"apps/web/a.txt": "a\n"})
    bad = box.branch("feat/bad", {"BAD_GUARD": "x\n", "apps/web/b.txt": "b\n"})
    box.g("checkout", "-q", "feat/clean")
    # dependency directories of the main checkout: two that the commit has a place for, one it has not
    nm = box.work / "node_modules"
    (nm / "pkg").mkdir(parents=True)
    (nm / "pkg/index.js").write_text("keep\n", encoding="utf-8")
    deep = box.work / "apps/web/node_modules/dep"
    deep.mkdir(parents=True)
    (deep / "x.js").write_text("keep\n", encoding="utf-8")
    ghost = box.work / "apps/ghost/node_modules/z"
    ghost.mkdir(parents=True)
    (ghost / "z.js").write_text("keep\n", encoding="utf-8")
    log = box.root / "cwd.log"

    def rows() -> list:
        out = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        if log.exists():
            log.unlink()
        return out

    def survives(label: str) -> None:
        t.check("... node_modules contents survive (%s)" % label,
                (nm / "pkg/index.js").read_text(encoding="utf-8") == "keep\n"
                and (deep / "x.js").is_file() and (ghost / "z.js").is_file())

    def fg(*args: str, env: dict | None = None) -> R:
        return box.script("fast_guards.py", "--base-ref", "origin/main", *args,
                          env={"GATE_TEST_CWDLOG": str(log), **(env or {})})

    # HEAD (feat/clean) is fine, the commit named is not
    r = fg("--commit", bad, env={"GATE_TEST_NMWRITE": "1"})
    got = rows()
    t.eq("a failing pushed commit, clean HEAD: exit 1", r.code, 1)
    t.has("... the failing guard is named", r.out, "FAIL guards: command failed")
    t.has("... with its output", r.out.split("FAIL guards:", 1)[-1], "BAD_GUARD file present")
    t.has("... and says where it checks", r.out, "checking pushed commit %s" % bad[:10])
    t.eq("... both guards ran", [x["step"] for x in got], ["guards", "secret-scan"])
    t.check("... in a worktree under .delivery/push-check/ named after the commit",
            all((".delivery/push-check/%s-" % bad[:12]) in x["cwd"] for x in got), str(got))
    t.eq("... {base} is still the merge base", got[1]["args"] if len(got) > 1 else None, [box.main_sha])
    t.check("... the logs are in the main checkout",
            (box.work / ".delivery/logs/pre-push/guards.log").is_file())
    t.eq("... no Rust target directory to share: CARGO_TARGET_DIR unset", got[0]["cargo"] if got else 1, None)
    t.eq("... node_modules of the main checkout is there, at the same place", got[0]["nm"] if got else 1, ["pkg"])
    t.eq("... so is a nested one", got[0]["deep"] if got else 1, ["dep"])
    t.eq("... one the commit has no place for is not", got[0]["ghost"] if got else 1, False)
    t.eq("... they are links, not copies", got[0]["nm_link"] if got else None, True)
    t.check("... without a warning about a link that could not be made", "warning" not in r.text, r.text)
    t.check("... a write through the link reached the main checkout", (nm / "probe.txt").is_file())
    (nm / "probe.txt").unlink(missing_ok=True)
    t.eq("... the worktree is gone", push_leftovers(box), [])
    survives("failing commit")
    t.check("... the checkout is as it was",
            box.g("rev-parse", "HEAD") == clean and box.clean() and not (box.work / "BAD_GUARD").exists())

    # the reverse: HEAD fails, the commit named is clean
    box.g("checkout", "-q", "feat/bad")
    r = fg("--commit", clean)
    got = rows()
    t.eq("HEAD failing, the commit named clean: exit 0", r.code, 0)
    t.check("... judged in a worktree of the named commit",
            bool(got) and all((".delivery/push-check/%s-" % clean[:12]) in x["cwd"] for x in got), str(got))
    t.eq("... the worktree is gone", push_leftovers(box), [])
    survives("clean commit")

    # --commit with the checked-out commit, and no --commit: in place
    for label, extra in (("--commit HEAD", ["--commit", "HEAD"]), ("--commit <HEAD sha>", ["--commit", bad]),
                         ("no --commit", [])):
        r = fg(*extra)
        got = rows()
        t.eq("%s: judges the checked-out (failing) commit" % label, r.code, 1)
        t.check("... in place", bool(got) and all(
            os.path.realpath(x["cwd"]) == os.path.realpath(str(box.work)) for x in got), str(got))
        t.eq("... without a worktree", push_leftovers(box), [])
        t.check("... or a push-check directory", not (box.work / ".delivery/push-check").exists())

    r = fg("--commit", "no-such-commit")
    t.eq("an unknown --commit: exit 2", r.code, 2)
    t.has("... and says so", r.err, "--commit")

    # Rust: the main checkout's target directory is shared
    (box.work / "target").mkdir()
    r = fg("--commit", clean)
    got = rows()
    t.check("a target/ in the main checkout becomes CARGO_TARGET_DIR",
            bool(got) and got[0]["cargo"] is not None
            and os.path.realpath(got[0]["cargo"]) == os.path.realpath(str(box.work / "target")), str(got))
    fg("--commit", clean, env={"CARGO_TARGET_DIR": "somewhere-else"})
    got = rows()
    t.eq("... unless the caller already set one", got[0]["cargo"] if got else None, "somewhere-else")
    fg("--commit", clean)
    rows()
    (box.work / "target").rmdir()

    # an interrupt (Ctrl-C) while the steps run: driven in-process, so it works everywhere
    driver = box.root / "_interrupt.py"
    driver.write_text(
        "import signal, sys\n"
        "sys.path.insert(0, 'scripts/delivery')\n"
        "import delivery_common as dc\n"
        "import fast_guards\n"
        "def boom(*a, **k):\n"
        "    if sys.argv[2] == 'term':\n"
        "        signal.raise_signal(signal.SIGTERM)\n"
        "    raise KeyboardInterrupt\n"
        "dc.execute_steps = boom\n"
        "dc.main_guard(lambda: fast_guards.main(['--base-ref', 'origin/main', '--commit', sys.argv[1]]))\n",
        encoding="utf-8")
    r = run([PY, driver, clean, "int"], cwd=box.work)
    t.eq("an interrupt during the steps: exit 130", r.code, 130)
    t.eq("... the worktree is gone", push_leftovers(box), [])
    survives("interrupt")
    r = run([PY, driver, clean, "term"], cwd=box.work)
    t.eq("a termination signal during the steps: exit 130", r.code, 130)
    t.eq("... the worktree is gone", push_leftovers(box), [])
    survives("termination")

    # a guard that hangs, with a child that would outlive it
    cfg = Box.gate_json()
    for st_ in cfg["steps"]:
        if st_["name"] == "guards":
            st_["run"] = '"%s" scripts/delivery/_slow.py' % PY
    box = Box(shared, gate_json=cfg)
    (box.work / ".git/info/exclude").write_text("node_modules/\n", encoding="utf-8")
    other = box.branch("feat/other", {"apps/web/a.txt": "a\n"})
    box.branch("feat/here", {"apps/web/b.txt": "b\n"})
    nm = box.work / "node_modules"
    (nm / "pkg").mkdir(parents=True)
    (nm / "pkg/index.js").write_text("keep\n", encoding="utf-8")
    deep = box.work / "apps/web/node_modules/dep"
    deep.mkdir(parents=True)
    (deep / "x.js").write_text("keep\n", encoding="utf-8")
    ghost = box.work / "apps/ghost/node_modules/z"
    ghost.mkdir(parents=True)
    (ghost / "z.js").write_text("keep\n", encoding="utf-8")
    started = time.monotonic()
    r = box.script("fast_guards.py", "--base-ref", "origin/main", "--commit", other, "--timeout-minutes", "0.05")
    elapsed = time.monotonic() - started
    t.eq("a step over its limit in the pushed commit's worktree: exit 1", r.code, 1)
    t.check("... stopped near the limit, not when the child ends", elapsed < 25, "%.1f s" % elapsed)
    t.has("... the FAIL line says it timed out", r.out, "FAIL guards: timed out after 0.05 min")
    t.eq("... the worktree is gone", push_leftovers(box), [])
    survives("timeout")

    if os.name != "nt":  # a real signal; Windows has no catchable equivalent for a child process
        for sig in (signal.SIGINT, signal.SIGTERM):
            proc = subprocess.Popen(
                [PY, "scripts/delivery/fast_guards.py", "--base-ref", "origin/main", "--commit", other],
                cwd=box.work, env=env_with(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pc = box.work / ".delivery/push-check"
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not (pc.is_dir() and any(pc.iterdir())):
                time.sleep(0.1)
            time.sleep(1.5)  # inside the slow step now
            proc.send_signal(sig)
            try:
                proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            t.eq("%s while a step runs: the run ends (130)" % sig.name, proc.returncode, 130)
            t.eq("... the worktree is gone", push_leftovers(box), [])
            survives(sig.name)


def sc_hook(t: T, shared: Path) -> None:
    box = Box(shared)
    box.g("config", "core.hooksPath", ".githooks")
    box.branch("feat/hk", {"apps/web/a.txt": "a\n"})
    r = run(["git", "push", "-q", "-u", "origin", "feat/hk"], cwd=box.work)
    t.eq("push with passing guards: allowed", r.code, 0)
    t.eq("... the guards ran once", [x[0] for x in box.ran()], ["guards", "secret-scan"])
    t.eq("... a new branch compares with the default branch", box.ran()[1], ["secret-scan", box.main_sha])
    t.check("... and the branch arrived", box.remote_ref("refs/heads/feat/hk") is not None)

    first_tip = box.g("rev-parse", "HEAD")
    box.commit({"apps/web/b.txt": "b\n"}, "second")
    box.clear_log()
    r = run(["git", "push", "-q", "origin", "feat/hk"], cwd=box.work)
    t.eq("an update compares with what the remote had", box.ran()[1], ["secret-scan", first_tip])

    second_tip = box.g("rev-parse", "HEAD")
    box.commit({"apps/web/c.txt": "c\n"}, "third")
    box.clear_log()
    r = run(["git", "push", "origin", "feat/hk"], cwd=box.work, extra_env={"GATE_TEST_FAIL": "guards"})
    t.check("push with a failing guard: blocked", r.code != 0, r.text)
    t.has("... with a one-line hint", r.text, "pre-push: blocked")
    t.eq("... and the remote did not move", box.remote_ref("refs/heads/feat/hk"), second_tip)

    box.clear_log()
    r = run(["git", "push", "origin", ":feat/hk"], cwd=box.work, extra_env={"GATE_TEST_FAIL": "guards"})
    t.eq("deleting a branch skips the hook", (r.code, box.ran()), (0, []))
    t.eq("... and deletes it", box.remote_ref("refs/heads/feat/hk"), None)

    box.g("tag", "v1")
    r = run(["git", "push", "origin", "v1"], cwd=box.work, extra_env={"GATE_TEST_FAIL": "guards"})
    t.eq("pushing a tag skips the hook", (r.code, box.ran()), (0, []))

    # the gate publishes its result with the hook enabled, even when a guard fails
    box.branch("feat/hk2", {"apps/web/d.txt": "d\n"})
    box.clear_log()
    r = box.gate(env={"GATE_TEST_FAIL": "guards"})
    t.eq("gate with a failing guard: exit 1", r.code, 1)
    t.check("... still publishes (the result ref is not guarded)",
            box.remote_ref("refs/gate-results/feat/hk2") is not None)
    t.eq("... and the hook did not run the guards again",
         len([x for x in box.ran() if x[0] == "guards"]), 1)

    # pushing a branch that is not checked out: the guards judge the pushed commit
    # (a temporary worktree), not whatever is checked out
    cwd_log = box.root / "hook-cwd.log"
    env = {"GATE_TEST_CWDLOG": str(cwd_log)}
    cl = box.branch("feat/cl", {"apps/web/o.txt": "o\n"})
    bad = box.branch("feat/bad", {"BAD_GUARD": "x\n", "apps/web/p.txt": "p\n"})

    def rows() -> list:
        return [json.loads(l) for l in cwd_log.read_text().splitlines()] if cwd_log.exists() else []

    def reset() -> None:
        if cwd_log.exists():
            cwd_log.unlink()

    box.g("checkout", "-q", "feat/cl")
    r = run(["git", "push", "origin", "feat/bad"], cwd=box.work, extra_env=env)
    t.check("pushing another branch whose commit fails a guard: blocked", r.code != 0, r.text)
    t.has("... the failing guard is named", r.text, "FAIL guards")
    t.eq("... and the remote did not get it", box.remote_ref("refs/heads/feat/bad"), None)
    t.check("... the guards ran in a temporary worktree of the pushed commit",
            bool(rows()) and all((".delivery/push-check/%s-" % bad[:12]) in x["cwd"] for x in rows()), str(rows()))
    t.check("... which is gone", not push_leftovers(box), str(push_leftovers(box)))
    t.check("... and the checked-out branch was not touched",
            box.g("rev-parse", "HEAD") == cl and box.clean() and not (box.work / "BAD_GUARD").exists())
    t.check("... no 'checked-out commit' note any more", "checked-out commit" not in r.text, r.text)

    reset()
    r = run(["git", "push", "-q", "origin", "feat/cl"], cwd=box.work, extra_env=env)
    t.eq("pushing the checked-out branch when clean: allowed", r.code, 0)
    t.check("... the guards ran in place",
            bool(rows()) and all(os.path.realpath(x["cwd"]) == os.path.realpath(str(box.work)) for x in rows()), str(rows()))
    t.eq("... and made no worktree", push_leftovers(box), [])

    box.g("checkout", "-q", "feat/bad")
    reset()
    r = run(["git", "push", "origin", "feat/bad"], cwd=box.work, extra_env=env)
    t.check("pushing the checked-out branch when its commit fails: blocked", r.code != 0, r.text)
    t.eq("... and the remote did not get it", box.remote_ref("refs/heads/feat/bad"), None)

    # the reverse: HEAD fails, the pushed commit is clean
    cl2 = box.branch("feat/cl2", {"apps/web/r.txt": "r\n"})
    box.g("checkout", "-q", "feat/bad")
    reset()
    r = run(["git", "push", "-q", "origin", "feat/cl2"], cwd=box.work, extra_env=env)
    t.eq("HEAD fails a guard, the pushed branch is clean: allowed", r.code, 0)
    t.eq("... the branch arrived", box.remote_ref("refs/heads/feat/cl2"), cl2)
    t.check("... it was judged in a worktree, not in the failing checkout",
            bool(rows()) and all((".delivery/push-check/%s-" % cl2[:12]) in x["cwd"] for x in rows()), str(rows()))
    t.eq("... which is gone", push_leftovers(box), [])

    # two refs in one push: each is judged, one failure blocks the push
    reset()
    box.g("checkout", "-q", "feat/cl")
    fresh = box.branch("feat/fresh", {"apps/web/q.txt": "q\n"})
    box.g("checkout", "-q", "feat/cl")
    r = run(["git", "push", "origin", "feat/fresh", "feat/bad"], cwd=box.work, extra_env=env)
    t.check("two refs in one push, one failing: blocked", r.code != 0, r.text)
    t.eq("... neither arrived", (box.remote_ref("refs/heads/feat/fresh"), box.remote_ref("refs/heads/feat/bad")), (None, None))
    t.eq("... each was judged in a worktree of its own commit",
         sorted({x["cwd"].rsplit("/", 1)[-1].rsplit("-", 1)[0] for x in rows()}), sorted([fresh[:12], bad[:12]]))
    t.eq("... and no worktree is left", push_leftovers(box), [])
    box.g("checkout", "-q", "feat/hk2")

    # no usable Python
    stubs = box.root / "stubs"
    stubs.mkdir()
    for name in ("python3", "python"):
        p = stubs / name
        p.write_text("#!/bin/sh\nexit 1\n", newline="\n")
        p.chmod(0o755)
    path = str(stubs) + os.pathsep + os.environ.get("PATH", "")
    box.commit({"apps/web/e.txt": "e\n"}, "fourth")
    r = run(["git", "push", "origin", "feat/hk2"], cwd=box.work, extra_env={"PATH": path})
    t.check("scripts present but Python missing: blocked", r.code != 0, r.text)
    t.has("... with instructions", r.text, "Python 3.11")

    shutil.rmtree(box.work / "scripts/delivery")
    r = run(["git", "push", "origin", "feat/hk2"], cwd=box.work, extra_env={"PATH": path})
    t.eq("scripts/delivery absent: allowed", r.code, 0)
    t.has("... with a warning", r.text, "NOT run")


def sc_hook_auto(t: T, shared: Path) -> None:
    """U3: the hook passes --base-ref auto for a ref the remote does not have, and only then."""
    box = fork_box(shared)
    integ = box.g("rev-parse", "integ")
    box.g("config", "core.hooksPath", ".githooks")
    box.branch("feat/h", {"apps/web/h.txt": "h\n"}, frm="integ")
    box.clear_log()
    r = run(["git", "push", "-q", "-u", "origin", "feat/h"], cwd=box.work)
    t.eq("a new branch cut from an integration branch: allowed", r.code, 0)
    t.has("... the hook asked for the fork point", r.text, "base: origin/integ (fork point)")
    t.eq("... and the guards compared with that branch", box.ran()[1], ["secret-scan", integ])

    first = box.g("rev-parse", "HEAD")
    box.commit({"apps/web/h2.txt": "h\n"}, "second")
    box.clear_log()
    r = run(["git", "push", "-q", "origin", "feat/h"], cwd=box.work)
    t.eq("an update compares with what the remote had", box.ran()[1], ["secret-scan", first])
    t.check("... and does not look for a fork point", "fork point" not in r.text, r.text)


def sc_hook_local(t: T, shared: Path) -> None:
    """The project's own check, kept beside the template as pre-push.local."""
    box = Box(shared)
    box.g("config", "core.hooksPath", ".githooks")
    local = box.work / ".githooks/pre-push.local"
    stdin_log = box.work / ".delivery/local.stdin"
    args_log = box.work / ".delivery/local.args"

    def install(code: int, executable: bool = True) -> None:
        box.write(".githooks/pre-push.local",
                  '#!/bin/sh\nmkdir -p .delivery\ncat > .delivery/local.stdin\n'
                  'echo "$@" > .delivery/local.args\nexit %d\n' % code)
        local.chmod(0o755 if executable else 0o644)

    def reset() -> None:
        box.clear_log()
        for p in (stdin_log, args_log):
            if p.exists():
                p.unlink()

    # no pre-push.local: as before
    box.branch("feat/loc", {"apps/web/a.txt": "a\n"})
    r = run(["git", "push", "-q", "-u", "origin", "feat/loc"], cwd=box.work)
    t.eq("no pre-push.local: the push is allowed", r.code, 0)
    t.eq("... the guards ran", [x[0] for x in box.ran()], ["guards", "secret-scan"])
    t.eq("... nothing else ran", stdin_log.exists(), False)
    pushed = box.g("rev-parse", "HEAD")

    # pre-push.local that fails
    install(1)
    box.commit({"apps/web/b.txt": "b\n"}, "second")
    reset()
    r = run(["git", "push", "origin", "feat/loc"], cwd=box.work)
    t.check("a failing pre-push.local blocks the push", r.code != 0, r.text)
    t.has("... and says why", r.text, "pre-push.local")
    t.eq("... the remote did not move", box.remote_ref("refs/heads/feat/loc"), pushed)
    t.eq("... the guards ran first", [x[0] for x in box.ran()], ["guards", "secret-scan"])

    # pre-push.local that passes, and what it receives
    install(0)
    reset()
    tip = box.g("rev-parse", "HEAD")
    r = run(["git", "push", "origin", "feat/loc"], cwd=box.work)
    t.eq("a passing pre-push.local lets the push through", r.code, 0)
    t.eq("... the branch arrived", box.remote_ref("refs/heads/feat/loc"), tip)
    stdin_text = stdin_log.read_text(encoding="utf-8") if stdin_log.exists() else ""
    t.has("... it received the ref line on stdin", stdin_text, "refs/heads/feat/loc %s refs/heads/feat/loc %s" % (tip, pushed))
    t.eq("... the guards still got the same stdin", [x[0] for x in box.ran()], ["guards", "secret-scan"])
    t.eq("... and compared with what the remote had", box.ran()[1], ["secret-scan", pushed])
    t.eq("... it received the remote name and url", args_log.read_text(encoding="utf-8").split()[0] if args_log.exists() else "",
         "origin")

    # a file without the executable bit still runs
    install(1, executable=False)
    box.commit({"apps/web/c.txt": "c\n"}, "third")
    reset()
    r = run(["git", "push", "origin", "feat/loc"], cwd=box.work)
    t.check("a pre-push.local without the executable bit runs, and blocks", r.code != 0 and stdin_log.exists(), r.text)

    # the local check runs only after the guards pass
    install(0)
    reset()
    r = run(["git", "push", "origin", "feat/loc"], cwd=box.work, extra_env={"GATE_TEST_FAIL": "guards"})
    t.check("a failing guard still blocks", r.code != 0, r.text)
    t.eq("... and pre-push.local did not run", stdin_log.exists(), False)

    # scripts/delivery absent: the project's check still runs
    shutil.rmtree(box.work / "scripts/delivery")
    install(1)
    reset()
    r = run(["git", "push", "origin", "feat/loc"], cwd=box.work)
    t.check("scripts/delivery absent: a failing pre-push.local still blocks", r.code != 0 and stdin_log.exists(), r.text)


def sc_fast_report(t: T, shared: Path) -> None:
    """fast_guards.py reports a failure like the gate, limits each step, keeps logs of its own."""
    box = Box(shared)
    box.branch("feat/fr", {"apps/web/a.txt": "a\n"})
    r = box.script("fast_guards.py", "--base-ref", "origin/main",
                   env={"GATE_TEST_FAIL": "guards", "GATE_TEST_NOISE": "guards"})
    t.eq("a failing guard: exit 1", r.code, 1)
    m = re.search(r"^FAIL guards: command failed \(exit 1, [\d.]+s\) - log: \.delivery/logs/pre-push/guards\.log\r?$",
                  r.out, re.M)
    t.check("the FAIL line names the step, the reason, the exit code and the log", m is not None, r.out[-500:])
    after = r.out.split("FAIL guards:", 1)[-1]
    t.eq("... followed by the last 40 lines of its output", len(re.findall(r"noise line \d+", after)), 40)
    t.check("... which are the last ones", "noise line 100" in after and "noise line 060" not in after)
    t.check("a passing step prints no FAIL line", "FAIL secret-scan" not in r.out)
    t.check("the log is where the line says",
            (box.work / ".delivery/logs/pre-push/guards.log").is_file())
    t.eq("... and is not the branch gate's", (box.work / ".delivery/logs/guards.log").exists(), False)
    t.has("the limit is shown: 5 min per step by default", r.out, "limit 5 min per step")
    t.eq("the other step still ran after the failure", [x[0] for x in box.ran()], ["guards", "secret-scan"])
    r = box.script("fast_guards.py", "--base-ref", "origin/main")
    t.eq("passing guards: exit 0, no FAIL line", (r.code, "FAIL " in r.out), (0, False))
    t.eq("--timeout-minutes 0: exit 2", box.script("fast_guards.py", "--timeout-minutes", "0").code, 2)

    # a guard that hangs, with a child that would outlive it
    cfg = Box.gate_json()
    for st_ in cfg["steps"]:
        if st_["name"] == "guards":
            st_["run"] = '"%s" scripts/delivery/_slow.py' % PY
    box = Box(shared, gate_json=cfg)
    box.branch("feat/frslow", {"apps/web/a.txt": "a\n"})
    started = time.monotonic()
    r = box.script("fast_guards.py", "--base-ref", "origin/main", "--timeout-minutes", "0.05")
    elapsed = time.monotonic() - started
    t.eq("a step over its limit: exit 1", r.code, 1)
    t.check("... stopped near the limit (3 s), not when the child ends (30 s)", elapsed < 25, "%.1f s" % elapsed)
    t.has("... the FAIL line says it timed out", r.out, "FAIL guards: timed out after 0.05 min")
    t.has("... and the output so far is shown", r.out.split("FAIL guards:", 1)[-1], "slow step started")
    t.eq("... the next step still ran", [x[0] for x in box.ran()], ["secret-scan"])
    beat = box.work / ".delivery/child.beat"
    before = beat.stat().st_size if beat.exists() else 0
    time.sleep(1.5)
    t.check("... and the child ran, then was killed with the step",
            before > 0 and (beat.stat().st_size if beat.exists() else 0) == before)

    # two runs at once in one checkout (two pushes): each reports its own output
    box = Box(shared)
    box.branch("feat/frpar", {"apps/web/a.txt": "a\n"})

    def start(mark: str, hold: str) -> subprocess.Popen:
        return subprocess.Popen(
            [PY, "scripts/delivery/fast_guards.py", "--base-ref", "origin/main"], cwd=box.work,
            env=env_with({"GATE_TEST_FAIL": "guards", "GATE_TEST_MARK": mark, "GATE_TEST_HOLD": hold}),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    first = start("AAA", "4")
    time.sleep(1.5)  # the first is inside its guards step now
    second = start("BBB", "0")
    out_b = second.communicate()[0].decode("utf-8", "replace")
    out_a = first.communicate()[0].decode("utf-8", "replace")
    tail_a = out_a.split("FAIL guards:", 1)[-1]
    tail_b = out_b.split("FAIL guards:", 1)[-1]
    t.eq("two runs at once: both report the failure", ("FAIL guards:" in out_a, "FAIL guards:" in out_b), (True, True))
    t.check("... each tail is its own run's output, not the other's",
            "mark AAA" in tail_a and "mark BBB" not in tail_a and "mark BBB" in tail_b and "mark AAA" not in tail_b,
            "A:\n%s\nB:\n%s" % (tail_a[-400:], tail_b[-400:]))


def sc_parallel(t: T, shared: Path) -> None:
    """Pushes from several worktrees at once: nothing is shared between the hook runs."""
    box = Box(shared)
    box.g("config", "core.hooksPath", ".githooks")
    trees = {}
    for name in ("a", "b", "c"):
        wt = box.root / ("wt-" + name)
        box.g("worktree", "add", "-q", wt.as_posix(), "-b", "par/" + name, "main")
        (wt / "apps/web").mkdir(parents=True, exist_ok=True)
        (wt / ("apps/web/%s.txt" % name)).write_text(name + "\n", encoding="utf-8")
        box.g("add", "-A", cwd=wt)
        box.g("commit", "-q", "-m", "work " + name, cwd=wt)
        trees[name] = wt
    procs = {
        n: subprocess.Popen(["git", "push", "-q", "-u", "origin", "par/" + n], cwd=wt,
                            env=env_with({"GATE_TEST_HOLD": "2.5"}),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for n, wt in trees.items()
    }
    out = {n: pr.communicate() for n, pr in procs.items()}
    t.eq("three pushes at once, each through the hook: all allowed",
         {n: pr.returncode for n, pr in procs.items()}, {"a": 0, "b": 0, "c": 0})
    t.eq("... every branch arrived", [box.remote_ref("refs/heads/par/" + n) is not None for n in trees], [True] * 3)
    ran = {}
    for n, wt in trees.items():
        log = wt / ".delivery/ran.log"
        ran[n] = [json.loads(l)[0] for l in log.read_text().splitlines()] if log.exists() else []
    t.eq("... each worktree ran its own guards once", ran, {n: ["guards", "secret-scan"] for n in trees})
    t.check("... each with logs of its own",
            all((wt / ".delivery/logs/pre-push/guards.log").is_file() for wt in trees.values()))

    # one failing in the middle of the others does not leak into them
    for n, wt in trees.items():
        (wt / ("apps/web/%s2.txt" % n)).write_text("2\n", encoding="utf-8")
        box.g("add", "-A", cwd=wt)
        box.g("commit", "-q", "-m", "more " + n, cwd=wt)
    procs = {
        n: subprocess.Popen(["git", "push", "-q", "origin", "par/" + n], cwd=wt,
                            env=env_with({"GATE_TEST_HOLD": "1.5", **({"GATE_TEST_FAIL": "guards"} if n == "b" else {})}),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for n, wt in trees.items()
    }
    for pr in procs.values():
        pr.communicate()
    t.eq("a guard failing in one worktree blocks only that push",
         {n: pr.returncode == 0 for n, pr in procs.items()}, {"a": True, "b": False, "c": True})


def sc_hook_ranges(t: T, shared: Path) -> None:
    """What the secret scan covers: first push, update, force-push, a remote sha we do not have."""
    box = Box(shared)
    box.g("config", "core.hooksPath", ".githooks")
    box.branch("feat/r", {"apps/web/a.txt": "a\n"})
    r = run(["git", "push", "-q", "-u", "origin", "feat/r"], cwd=box.work)
    t.eq("first push of a branch: allowed", r.code, 0)
    t.eq("... the scan covers everything since the default branch", box.ran()[1], ["secret-scan", box.main_sha])
    tip1 = box.g("rev-parse", "HEAD")

    box.g("commit", "-q", "--amend", "-m", "rewritten")
    box.clear_log()
    r = run(["git", "push", "-q", "--force", "origin", "feat/r"], cwd=box.work)
    t.eq("force-push of rewritten history: allowed", r.code, 0)
    t.eq("... the scan starts at the fork point, not at the old tip", box.ran()[1], ["secret-scan", box.main_sha])
    t.check("... which is not the discarded commit", tip1 != box.g("rev-parse", "HEAD"))

    # someone else moved the branch: its tip is not in this clone
    other = box.root / "other"
    run(["git", "clone", "-q", box.origin.as_posix(), other.as_posix()])
    run(["git", "checkout", "-q", "feat/r"], cwd=other)
    (other / "apps/web").mkdir(parents=True, exist_ok=True)
    (other / "apps/web/theirs.txt").write_text("t\n", encoding="utf-8")
    run(["git", "add", "-A"], cwd=other)
    run(["git", "commit", "-q", "-m", "theirs"], cwd=other)
    run(["git", "push", "-q", "origin", "feat/r"], cwd=other)
    theirs = run(["git", "rev-parse", "HEAD"], cwd=other).out.strip()
    t.eq("(the other clone moved the branch)", box.remote_ref("refs/heads/feat/r"), theirs)
    t.eq("(and this clone does not have its tip)",
         run(["git", "cat-file", "-e", theirs + "^{commit}"], cwd=box.work).code != 0, True)
    box.commit({"apps/web/mine.txt": "m\n"}, "mine")
    box.clear_log()
    r = run(["git", "push", "-q", "--force", "origin", "feat/r"], cwd=box.work)
    t.eq("force-push over a tip this clone does not have: allowed", r.code, 0)
    t.eq("... the scan falls back to the default branch", box.ran()[1], ["secret-scan", box.main_sha])

    # no default branch to compare with: the push is blocked, and says why
    box.branch("feat/r2", {"apps/web/b.txt": "b\n"})
    box.g("update-ref", "-d", "refs/remotes/origin/main")
    box.g("update-ref", "-d", "refs/remotes/origin/feat/r")  # no other remote branch for a fork point either
    # and nothing to fetch it from (fetches fail; pushes still reach the real origin)
    box.g("remote", "set-url", "--push", "origin", box.origin.as_posix())
    box.g("remote", "set-url", "origin", (box.root / "gone.git").as_posix())
    box.clear_log()
    r = run(["git", "push", "-q", "-u", "origin", "feat/r2"], cwd=box.work)
    t.check("a first push with no origin/main: blocked", r.code != 0, r.text)
    t.has("... and says which ref is missing", r.text, "base ref")
    t.eq("... no step ran", box.ran(), [])


# --------------------------------------------------------------------------
# scenarios: join.py
# --------------------------------------------------------------------------

def join(box: Box, *args: str, env: dict | None = None) -> R:
    return box.script("join.py", *args, env=env)


def join_result(box: Box) -> dict:
    return json.loads((box.work / dc.JOIN_RESULT_PATH).read_text(encoding="utf-8"))


def integ_box(shared: Path) -> Box:
    box = Box(shared)
    box.g("checkout", "-q", "-B", "integ", "main")
    box.push("integ")
    return box


def sc_join_clean(t: T, shared: Path) -> None:
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/b", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    # the integration branch moves after both were gated: their bases are now older
    box.g("checkout", "-q", "integ")
    box.commit({"docs/other.txt": "o\n"}, "someone else")
    box.g("push", "-q", "origin", "integ")
    integ_before = box.g("rev-parse", "origin/integ")
    box.clear_log()

    r = join(box, "--into", "integ", "feat/a", "feat/b")
    t.eq("clean join with older bases: exit 0", r.code, 0)
    subjects = box.g("log", "--merges", "--format=%s", "integ").splitlines()
    t.eq("merge commits are named Join <branch>, in order", subjects, ["Join feat/b", "Join feat/a"])
    t.eq("merges are real merge commits (--no-ff)",
         len(box.g("rev-list", "--parents", "-n1", "HEAD").split()), 3)
    t.check("both branches' work is in the joined head",
            all((box.work / f).exists() for f in ("apps/web/a.txt", "apps/api/b.txt", "docs/other.txt")))
    jr = join_result(box)
    t.eq("join-result.json: joined, no stop", (jr["joined"], jr["stopped_at"], jr["conflicts"]),
         (["feat/a", "feat/b"], None, []))
    qc = jr["quick_check"]
    t.eq("the quick check ran on the joined head", qc["head"], box.g("rev-parse", "HEAD"))
    t.eq("... against the default branch", qc["base_ref"], "origin/main")
    t.eq("... covering both branches' packages", qc["changed_dirs"], ["apps/api", "apps/web"])
    t.eq("... and passed", qc["pass"], True)
    t.eq("nothing pushed without --push", box.g("rev-parse", "origin/integ"), integ_before)
    t.eq("... and no result published without --push", box.remote_ref("refs/gate-results/integ"), None)
    t.eq("working tree left clean", box.clean(), True)

    # --push, in a second box
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/b", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    r = join(box, "--into", "integ", "feat/a", "feat/b", "--push")
    t.eq("--push: exit 0", r.code, 0)
    head = box.g("rev-parse", "HEAD")
    t.eq("a branch that could fast-forward still gets a merge commit",
         box.g("log", "--merges", "--format=%s", "integ").splitlines(), ["Join feat/b", "Join feat/a"])
    t.eq("--push: integration pushed", box.g("rev-parse", "origin/integ"), head)
    t.eq("--push: the quick check publishes no gate result (CI is the one full suite)",
         box.remote_ref("refs/gate-results/integ"), None)

    # --no-gate
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/a", "--no-gate")
    t.eq("--no-gate: exit 0, nothing ran", (r.code, box.ran()), (0, []))

    # a failing gate on the joined head blocks the push
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/b", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    before = box.g("rev-parse", "origin/integ")
    r = join(box, "--into", "integ", "feat/a", "feat/b", "--push", env={"GATE_TEST_FAIL": "typecheck"})
    t.eq("a failing light check on the joined head: exit 1", r.code, 1)
    t.eq("... and nothing is pushed", box.g("rev-parse", "origin/integ"), before)

    # preconditions
    r = join(box, "--into", "no-such-integration", "feat/a")
    t.eq("unknown integration branch: exit 2", r.code, 2)
    box.write("docs/dirty.txt", "d\n")
    r = join(box, "--into", "integ", "feat/a")
    t.eq("dirty working tree: exit 2", r.code, 2)


def sc_join_no_gate_config(t: T, shared: Path) -> None:
    """STACKSPEC 13.8: join.py works in a repository with no gate.json."""
    box = integ_box(shared)
    box.branch("feat/a", {"apps/web/a.txt": "a\n"}, "integ")
    box.push("feat/a")
    box.g("checkout", "-q", "integ")
    box.g("rm", "-q", "scripts/delivery/gate.json")
    box.g("commit", "-q", "-m", "no gate config")
    box.g("push", "-q", "origin", "integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/a")
    t.eq("no gate.json: exit 0, nothing ran", (r.code, box.ran()), (0, []))
    t.has("... says the gate is not configured", r.out, "gate is not configured")
    jr = join_result(box)
    t.eq("... records that no gate ran", (jr["joined"], jr["gate"], jr["quick_check"]),
         (["feat/a"], "not configured", {"skipped": "gate not configured"}))


def sc_join_same_tree(t: T, shared: Path) -> None:
    """DS45: the gate on the joined head is skipped when its tree is the tree of a joined
    branch head whose gate result is trusted for that head and for the gate's base."""
    # one branch joined onto an integration branch that is still at the base: same tree
    box = integ_box(shared)
    head = box.gated("feat/a", {"apps/web/a.txt": "a\n"}, base_ref="origin/main", frm="integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/a", "--push")
    t.eq("same tree as a trusted branch head: exit 0, no step ran", (r.code, box.ran()), (0, []))
    t.has("... and the output says the gate was skipped", r.out, "gate on the joined head skipped")
    t.has("... naming feat/a", r.out, "equals that of feat/a")
    t.eq("... the merge was pushed", box.g("rev-parse", "origin/integ"), box.g("rev-parse", "HEAD"))
    t.eq("... the tree is the branch's", box.g("rev-parse", "HEAD^{tree}"), box.g("rev-parse", head + "^{tree}"))

    # the branch was gated against a base that has since moved: its result is not trusted
    # for the gate's base, so the gate runs although the trees are equal
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, base_ref="origin/main", frm="integ")
    box.g("checkout", "-q", "main")
    box.commit({"apps/api/main-moves.txt": "m\n"}, "main moves")  # code, so not an inert move (DL1); integ does not have it
    box.g("push", "-q", "origin", "main")
    box.g("checkout", "-q", "integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/a")
    t.eq("a base that moved on after the branch was gated: the gate runs",
         (r.code, box.ran() != [], "skipped" in r.out), (0, True, False))

    # integration moved: the joined tree is not the branch's, whatever its result says
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, base_ref="origin/main", frm="integ")
    box.g("checkout", "-q", "integ")
    box.commit({"docs/other.txt": "o\n"}, "someone else")
    box.g("push", "-q", "origin", "integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/a")
    t.eq("the integration branch added work: the gate runs",
         (r.code, box.ran() != [], "skipped" in r.out), (0, True, False))

    # two branches: the joined tree equals neither
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, base_ref="origin/main", frm="integ")
    box.gated("feat/b", {"apps/api/b.txt": "b\n"}, base_ref="origin/main", frm="integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/a", "feat/b")
    t.eq("two branches joined: the gate runs",
         (r.code, box.ran() != [], "skipped" in r.out), (0, True, False))

    # a failing result is refused before anything can be skipped
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, base_ref="origin/main", frm="integ", fail="unit")
    r = join(box, "--into", "integ", "feat/a")
    t.eq("a failing result: join refuses, nothing skipped", (r.code, "skipped" in r.out), (1, False))


def sc_join_untrusted(t: T, shared: Path) -> None:
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/bad", {"apps/api/x.txt": "x\n"}, frm="integ", base_ref="origin/integ", fail="unit")
    box.branch("feat/ungated", {"apps/api/u.txt": "u\n"}, frm="integ")
    box.push("feat/ungated")
    box.gated("feat/stale", {"packages/core/s.txt": "s\n"}, frm="integ", base_ref="origin/integ")
    box.commit({"packages/core/s2.txt": "s2\n"}, "after the gate")
    box.push("feat/stale")
    before = box.g("rev-parse", "origin/integ")

    r = join(box, "--into", "integ", "feat/a", "feat/bad", "--no-gate")
    t.eq("a failing result: exit 1", r.code, 1)
    jr = join_result(box)
    t.eq("... stopped at that branch, after joining the good one", (jr["joined"], jr["stopped_at"]),
         (["feat/a"], "feat/bad"))
    t.check("... without merging it", not (box.work / "apps/api/x.txt").exists())

    r = join(box, "--into", "integ", "feat/ungated", "--no-gate")
    t.eq("no result: exit 2", r.code, 2)
    t.eq("... stopped_at names it", join_result(box)["stopped_at"], "feat/ungated")

    r = join(box, "--into", "integ", "feat/stale", "--no-gate")
    t.eq("stale head: exit 1", r.code, 1)
    t.eq("... nothing joined", join_result(box)["joined"], [])
    t.eq("nothing was pushed", box.g("rev-parse", "origin/integ"), before)


def sc_join_docs_strip(t: T, shared: Path) -> None:
    """DOCSPEC R10.3: join strips docs/work/ with luismc-docs' docs_work.py and keeps the summaries."""
    plugin = str(REPO / "claude/plugins/docs/scripts/docs_work.py")
    report = "# DOC9\n\nStatus: READY\n\nSummary: the thing works.\n"
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n", "docs/work/reports/DOC9.md": report, "docs/work/briefs/DOC9.md": "brief\n"},
              frm="integ", base_ref="origin/integ")
    r = join(box, "--into", "integ", "feat/a", env={"LUISMC_DOCS_WORK": plugin})
    t.eq("docs plugin present: exit 0", r.code, 0)
    t.eq("... docs/work/ is gone from the joined head", (box.work / "docs/work").exists(), False)
    t.check("... the work itself stays", (box.work / "apps/web/a.txt").exists())
    t.eq("... removal is its own commit", box.g("log", "-1", "--format=%s"), "Strip temporary agent docs")
    jr = join_result(box)
    t.eq("... summaries recorded", jr["docs_summaries"], ["- DOC9: the thing works."])
    t.eq("... stripped flag", jr["docs"]["stripped"], True)
    t.has("... summaries file for the PR body", (box.work / ".delivery/docs-summaries.md").read_text(), "- DOC9: the thing works.")

    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n", "docs/work/reports/DOC9.md": report}, frm="integ", base_ref="origin/integ")
    r = join(box, "--into", "integ", "feat/a", env={"LUISMC_DOCS_WORK": str(box.work / "no-such-docs-work.py")})
    t.eq("docs plugin absent: join still succeeds", r.code, 0)
    t.has("... says so", r.out, "luismc-docs is not installed")
    t.eq("... and leaves docs/work/ alone", (box.work / "docs/work/reports/DOC9.md").exists(), True)
    t.eq("... recorded as not stripped", join_result(box)["docs"]["stripped"], False)

    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = join(box, "--into", "integ", "feat/a", env={"LUISMC_DOCS_WORK": plugin})
    t.eq("plugin present, nothing under docs/work/: exit 0, no summaries", (r.code, join_result(box)["docs_summaries"]), (0, []))


def sc_join_conflicts(t: T, shared: Path) -> None:
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/shared.txt": "A\ntwo\nthree\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/c", {"apps/web/shared.txt": "C\ntwo\nthree\n", "apps/api/c.txt": "c\n"},
              frm="integ", base_ref="origin/integ")
    integ_tip = box.remote_ref("refs/heads/integ")
    r = join(box, "--into", "integ", "feat/a", "feat/c", "--no-gate")
    t.eq("a real conflict: exit 3", r.code, 3)
    jr = join_result(box)
    t.eq("join-result.json: joined, stopped_at, conflicts",
         (jr["joined"], jr["stopped_at"], jr["conflicts"]), (["feat/a"], "feat/c", ["apps/web/shared.txt"]))
    t.eq("the conflicting merge is aborted", (box.clean(), (box.work / ".git/MERGE_HEAD").exists()), (True, False))
    t.eq("the earlier join is kept", box.g("log", "-1", "--merges", "--format=%s"), "Join feat/a")
    t.eq("nothing pushed", box.remote_ref("refs/heads/integ"), integ_tip)
    t.has("the conflict is reported", r.err, "apps/web/shared.txt")

    # a lockfile-only conflict is resolved
    box = integ_box(shared)
    box.gated("feat/l1", {"pnpm-lock.yaml": "lock\nL1\nl2\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/l2", {"pnpm-lock.yaml": "lock\nL2\nl2\n", "apps/api/l2.txt": "l2\n"},
              frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/l1", "feat/l2", "--no-gate")
    t.eq("a lockfile-only conflict: exit 0", r.code, 0)
    t.eq("... integration's lockfile wins",
         (box.work / "pnpm-lock.yaml").read_text(encoding="utf-8"), "lock\nL1\nl2\n")
    t.eq("... the other work of the branch is in", (box.work / "apps/api/l2.txt").exists(), True)
    t.eq("... setup was re-run", [x[0] for x in box.ran(True)], ["setup"])
    t.eq("... it is a Join commit", box.g("log", "-1", "--format=%s"), "Join feat/l2")
    t.eq("... with two parents", len(box.g("rev-list", "--parents", "-n1", "HEAD").split()), 3)
    t.eq("... and a clean tree", box.clean(), True)
    jr = join_result(box)
    t.eq("... join-result.json lists both", (jr["joined"], jr["stopped_at"]), (["feat/l1", "feat/l2"], None))

    # ... unless setup then fails
    r = join(box, "--into", "integ", "feat/l1", "feat/l2", "--no-gate", env={"GATE_TEST_FAIL": "setup"})
    t.eq("lockfile conflict but setup fails: exit 3", r.code, 3)
    jr = join_result(box)
    t.eq("... stopped there, lockfile named", (jr["stopped_at"], jr["conflicts"]), ("feat/l2", ["pnpm-lock.yaml"]))
    t.eq("... merge aborted, tree clean", (box.clean(), (box.work / ".git/MERGE_HEAD").exists()), (True, False))

    # lockfile and source both conflict: not resolved
    box = integ_box(shared)
    box.gated("feat/m1", {"pnpm-lock.yaml": "lock\nM1\nl2\n", "apps/web/shared.txt": "M1\ntwo\nthree\n"},
              frm="integ", base_ref="origin/integ")
    box.gated("feat/m2", {"pnpm-lock.yaml": "lock\nM2\nl2\n", "apps/web/shared.txt": "M2\ntwo\nthree\n"},
              frm="integ", base_ref="origin/integ")
    r = join(box, "--into", "integ", "feat/m1", "feat/m2", "--no-gate")
    t.eq("lockfile plus source conflict: exit 3", r.code, 3)
    t.eq("... every conflicting path is listed", join_result(box)["conflicts"],
         ["apps/web/shared.txt", "pnpm-lock.yaml"])


# --------------------------------------------------------------------------
# agent_setup.sh
# --------------------------------------------------------------------------

def find_bash() -> str | None:
    if os.name == "nt":  # not WSL's bash: the one that ships with Git
        exec_path = run(["git", "--exec-path"]).out.strip()
        if exec_path:
            cand = Path(exec_path).parents[2] / "bin" / "bash.exe"
            if cand.exists():
                return cand.as_posix()
    return shutil.which("bash")


def expected_asset(version: str) -> str | None:
    system = platform.system()
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    os_name = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(system)
    if not arch or not os_name:
        return None
    return "gitleaks_%s_%s_%s.%s" % (version, os_name, arch, "zip" if os_name == "windows" else "tar.gz")


def sc_agent_setup(t: T, shared: Path) -> None:
    bash = find_bash()
    if bash is None:
        print("SKIP  agent_setup: no bash on this machine")
        return
    script = shared / "scripts/delivery/agent_setup.sh"
    syntax = run([bash, "-n", script.as_posix()])
    t.eq("agent_setup.sh parses", syntax.code, 0)

    pin = json.loads((shared / "scripts/delivery/tools.json").read_text())["gitleaks"]
    version = pin if isinstance(pin, str) else pin["version"]
    box = Box(shared)
    sh = box.work / "scripts/delivery/agent_setup.sh"
    path = Path(PY).parent.as_posix() + os.pathsep + os.environ.get("PATH", "")
    base_env = {"PATH": path}
    tools = box.work / "scripts/delivery/tools.json"

    # DS162: the old tools.json form ({"gitleaks": "x.y.z"}) has no pin and is refused.
    tools.write_text(json.dumps({"gitleaks": version}) + "\n")
    old = run([bash, sh.as_posix()], cwd=box.work, extra_env={**base_env, "DELIVERY_DRY_RUN": "1"})
    t.check("old tools.json form (no pin): refused", old.code != 0, old.code)
    t.has("... names tools_pin.py", old.err, "tools_pin.py")

    # a fake release, pinned in tools.json for this platform
    asset = expected_asset(version)
    if not asset:
        print("SKIP  agent_setup: no gitleaks asset for this OS and CPU")
        return
    exe = "gitleaks.exe" if asset.endswith(".zip") else "gitleaks"
    payload = ("#!/bin/sh\necho %s\n" % version).encode()
    if asset.endswith(".zip"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(exe, payload)
        archive = buf.getvalue()
    else:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(exe)
            info.size, info.mode = len(payload), 0o755
            tf.addfile(info, io.BytesIO(payload))
        archive = buf.getvalue()
    plat = asset[len("gitleaks_%s_" % version):].split(".", 1)[0]

    def write_pin(sha):
        tools.write_text(json.dumps({"gitleaks": {"version": version, "sha256": {plat: sha}}}) + "\n")
    write_pin(hashlib.sha256(archive).hexdigest())

    dry = run([bash, sh.as_posix()], cwd=box.work, extra_env={**base_env, "DELIVERY_DRY_RUN": "1"})
    t.eq("dry run: exit 0", dry.code, 0)
    url = dry.out.strip().splitlines()[-1] if dry.out.strip() else ""
    t.check("dry run: the URL points at the pinned release on GitHub",
            url.startswith("https://github.com/gitleaks/gitleaks/releases/download/v%s/" % version), url)
    t.eq("dry run: asset name for this OS and CPU", url.rsplit("/", 1)[-1], asset)

    # serve the fake release
    srv_dir = box.root / "release"
    srv_dir.mkdir()
    (srv_dir / asset).write_bytes(archive)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):  # keep the test output readable
            pass

    handler = functools.partial(Quiet, directory=str(srv_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        bin_dir = box.root / "bin"
        env = {**base_env, "DELIVERY_BIN": bin_dir.as_posix(), "DELIVERY_GITLEAKS_BASE_URL": base_url}
        r = run([bash, sh.as_posix()], cwd=box.work, extra_env=env)
        t.eq("install with a matching checksum: exit 0", r.code, 0)
        t.check("... gitleaks is in DELIVERY_BIN", (bin_dir / exe).exists(), r.text)
        t.eq("... gate.json setup ran", [x[0] for x in box.ran(True)], ["setup"])
        t.eq("... hooks path set", box.g("config", "--get", "core.hooksPath"), ".githooks")
        if exe == "gitleaks":
            box.clear_log()
            r = run([bash, sh.as_posix()], cwd=box.work, extra_env=env)
            t.eq("idempotent: second run exit 0", r.code, 0)
            t.has("idempotent: skips the download", r.err, "already installed")
            t.eq("idempotent: setup runs again", [x[0] for x in box.ran(True)], ["setup"])

        # the PATH hint is a shell path: through cygpath when there is one (Git Bash)
        # (a cygpath function from BASH_ENV, so it wins over any real cygpath on PATH)
        cyg_env = box.root / "cygpath.env"
        cyg_env.write_text('cygpath() { [ "$1" = "-u" ] || return 1; echo "/cyg$2"; }\n', newline="\n")
        cyg_bin = box.root / "cyg-bin"
        r = run([bash, sh.as_posix()], cwd=box.work,
                extra_env={**env, "DELIVERY_BIN": cyg_bin.as_posix(), "BASH_ENV": cyg_env.as_posix()})
        t.eq("with cygpath: exit 0", r.code, 0)
        t.has("... the PATH hint uses cygpath -u", r.err, 'export PATH="/cyg%s:$PATH"' % cyg_bin.as_posix())

        # a tampered archive (it no longer matches the pin) must not be installed
        write_pin("1" * 64)
        bad_bin = box.root / "bad-bin"
        r = run([bash, sh.as_posix()], cwd=box.work,
                extra_env={**env, "DELIVERY_BIN": bad_bin.as_posix()})
        t.eq("checksum mismatch: exit 2", r.code, 2)
        t.has("... says mismatch", r.err, "checksum mismatch")
        t.eq("... nothing installed", (bad_bin / exe).exists(), False)
    finally:
        server.shutdown()

    # no usable Python and no package manager
    stubs = box.root / "stubs"
    stubs.mkdir()
    for name in ("python3", "python", "apt-get", "brew", "sudo"):
        p = stubs / name
        p.write_text("#!/bin/sh\nexit 1\n", newline="\n")
        p.chmod(0o755)
    r = run([bash, sh.as_posix()], cwd=box.work,
            extra_env={"PATH": stubs.as_posix() + os.pathsep + os.environ.get("PATH", "")})
    t.eq("no Python 3.11+ and nothing to install it with: exit 2", r.code, 2)
    t.has("... with instructions", r.err, "Python 3.11+")


# --------------------------------------------------------------------------
# static checks: tools.json, gate.json per track, guard starters, packages
# --------------------------------------------------------------------------

def unfrozen_setup(cmds: list[str]) -> list[str]:
    """The setup commands that could change a lockfile or the dependency set."""
    bad = []
    for cmd in cmds:
        words = cmd.split()
        if words[:2] == ["pnpm", "install"] and "--frozen-lockfile" not in words:
            bad.append(cmd)
        elif words[:2] == ["npm", "install"] or words[:1] == ["yarn"] and "--frozen-lockfile" not in words:
            bad.append(cmd)
        elif words[:1] == ["cargo"] and "--locked" not in words:
            bad.append(cmd)
        elif words[:2] == ["dotnet", "restore"] and "--locked-mode" not in words:
            bad.append(cmd)
        elif words[:1] == ["go"] and (words[1:3] == ["mod", "tidy"] or words[1:2] == ["get"]
                                       or (words[1:2] == ["list"] and "-mod=readonly" not in words)):
            bad.append(cmd)
    return bad


def sc_assets(t: T, shared: Path) -> None:
    tools = json.loads((shared / "scripts/delivery/tools.json").read_text())
    ver = tools.get("gitleaks", "")
    if isinstance(ver, dict):  # the pinned form: version plus a SHA-256 per platform
        pins = ver.get("sha256", {})
        t.eq("tools.json pins the five platforms", sorted(pins),
             ["darwin_arm64", "darwin_x64", "linux_arm64", "linux_x64", "windows_x64"])
        t.check("... each pin is a SHA-256", all(re.fullmatch(r"[0-9a-f]{64}", v) for v in pins.values()), str(pins))
        ver = ver.get("version", "")
    t.check("tools.json pins gitleaks to an exact x.y.z", re.fullmatch(r"\d+\.\d+\.\d+", ver) is not None, ver)
    parts = tuple(int(x) for x in ver.split(".")) if re.fullmatch(r"\d+\.\d+\.\d+", ver) else (0, 0, 0)
    t.check("... new enough for the `git` subcommand (8.19+)", parts >= (8, 19, 0), ver)

    for track, kind in TRACKS.items():
        path = TOOLING / track / "scripts/delivery/gate.json"
        label = "%s gate.json" % track
        t.check(label + " exists", path.is_file())
        if not path.is_file():
            continue
        tmp = Path(tempfile.mkdtemp(dir=_TMP_ROOT))
        (tmp / "scripts/delivery").mkdir(parents=True)
        (tmp / "scripts/delivery/gate.json").write_bytes(path.read_bytes())
        try:
            cfg = dc.load_gate(tmp)
        except dc.DeliveryError as exc:
            t.check(label + " is valid", False, str(exc))
            continue
        t.check(label + " is valid", True)
        t.eq(label + ": track and package kind", (cfg["track"], cfg["packages"]["kind"]), (track, kind))
        t.check(label + ": setup installs from the lockfile in frozen mode",
                bool(cfg["setup"]) and not unfrozen_setup(cfg["setup"]), str(cfg["setup"]))
        raw = json.loads(path.read_text(encoding="utf-8"))
        t.check(label + ": timeout_minutes is set (an integer >= 1)",
                isinstance(raw.get("timeout_minutes"), int) and raw["timeout_minutes"] >= 1, str(raw.get("timeout_minutes")))
        steps = {s["name"]: s for s in cfg["steps"]}
        t.check(label + ": guards and secret-scan are pre_push and always",
                all(steps.get(n, {}).get("pre_push") and steps[n]["scope"] == "always"
                    for n in ("guards", "secret-scan")))
        t.check(label + ": secret-scan uses `gitleaks git` over {base}..HEAD",
                "gitleaks git " in steps["secret-scan"]["run"] and "--log-opts={base}..HEAD" in steps["secret-scan"]["run"])
        t.check(label + ": only known placeholders",
                all(set(re.findall(r"\{(\w+)\}", s.get("run", "") + s.get("run_full", ""))) <= {"base", "changed_dirs", "affected_dirs", "e2e_specs"}
                    for s in cfg["steps"]))
        t.check(label + ": has typecheck, lint-or-build and unit steps",
                {"typecheck", "unit"} <= set(steps))
        t.check(label + ": no single quotes in commands (cmd.exe)",
                all("'" not in s.get("run", "") + s.get("run_full", "") for s in cfg["steps"]))
    t.eq("a non-frozen setup is recognised",
         unfrozen_setup(["pnpm install", "cargo fetch", "dotnet restore", "go mod tidy", "go get x", "npm install",
                         "go list -m all"]),
         ["pnpm install", "cargo fetch", "dotnet restore", "go mod tidy", "go get x", "npm install", "go list -m all"])
    t.eq("a frozen setup is accepted",
         unfrozen_setup(["pnpm install --frozen-lockfile", "cargo fetch --locked", "dotnet restore --locked-mode",
                         "go mod download", "go list -mod=readonly -m all"]), [])
    ts = json.loads((TOOLING / "ts/scripts/delivery/gate.json").read_text())
    t.check("ts gate.json matches the contract example commands",
            any("--filter" in s["run"] and "{base}" in s["run"] for s in ts["steps"] if s["name"] == "typecheck")
            and any(s["name"] == "unit" and "{affected_dirs}" in s["run"] and "--project unit" in s["run"] and "--passWithNoTests" in s["run"] for s in ts["steps"]))
    e2e_step = {s["name"]: s for s in ts["steps"]}["e2e"]
    t.check("ts gate.json: the e2e step takes {e2e_specs}, run_full runs the whole suite",
            e2e_step["run"].endswith("playwright test {e2e_specs}") and "{e2e_specs}" not in e2e_step["run_full"]
            and e2e_step["run_full"].endswith("playwright test") and "e2e_map" not in ts, str(e2e_step))
    runners = {s["name"]: s for s in ts["steps"]}
    t.check("ts: the test-runner steps run with CI=true, as CI does (timeouts, forbidOnly)",
            all(runners[n].get("env") == {"CI": "true"} for n in ("unit", "guards", "e2e")),
            str({n: runners[n].get("env") for n in ("unit", "guards", "e2e")}))
    t.check("go guards select TestGuard*",
            "TestGuard" in next(s for s in json.loads((TOOLING / "go/scripts/delivery/gate.json").read_text())["steps"] if s["name"] == "guards")["run"])
    t.check("rust guards select guard_*",
            "guard_" in next(s for s in json.loads((TOOLING / "rust/scripts/delivery/gate.json").read_text())["steps"] if s["name"] == "guards")["run"])
    t.check("dotnet guards select Category=Guard",
            "Category=Guard" in next(s for s in json.loads((TOOLING / "dotnet/scripts/delivery/gate.json").read_text())["steps"] if s["name"] == "guards")["run"])

    # starter guard tests exist, follow their track's naming convention, and contain no marker themselves
    vitest = (TOOLING / "ts/vitest.config.ts").read_text(encoding="utf-8")
    t.check("ts vitest.config.ts has a `guard` project over **/*.guard.test.ts",
            "name: 'guard'" in vitest and "'**/*.guard.test.ts'" in vitest)
    starters = {
        "ts": (TOOLING / "ts/guards/no-conflict-markers.guard.test.ts", "describe("),
        "go": (TOOLING / "go/guards/conflict_markers_guard_test.go", "func TestGuard"),
        "rust": (TOOLING / "rust/crates/guards/tests/guard_conflict_markers.rs", "fn guard_"),
        "dotnet": (TOOLING / "dotnet/tests/Guards/NoConflictMarkersGuard.cs", 'Trait("Category", "Guard")'),
    }
    marker = re.compile(r"^(<{7}( |$)|={7}$|>{7}( |$))")
    for track, (path, needle) in starters.items():
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        t.check("%s starter guard exists and follows the convention" % track, needle in text, str(path))
        t.check("%s starter guard holds no conflict marker line itself" % track,
                not any(marker.match(l) for l in text.splitlines()))
    t.check("rust guard crate has a lib target", (TOOLING / "rust/crates/guards/src/lib.rs").is_file())
    t.check("dotnet guard project exists", (TOOLING / "dotnet/tests/Guards/Guards.csproj").is_file())
    guard_cfg = vitest[vitest.index("name: 'guard'"):]
    guard_cfg = guard_cfg[:guard_cfg.index("name: 'contract'")]
    t.check("ts guard project has a test timeout of its own, well above Vitest's 5 s default",
            (m := re.search(r"testTimeout:\s*([\d_]+)", guard_cfg)) is not None and int(m.group(1).replace("_", "")) >= 30000,
            guard_cfg)
    t.check("ts guard project does not run the copies in nested checkouts",
            "configDefaults.exclude" in guard_cfg and "nestedCheckouts" in guard_cfg
            and "'**/.claude/worktrees/**'" in vitest)
    ts_guard = (TOOLING / "ts/guards/no-conflict-markers.guard.test.ts").read_text(encoding="utf-8")
    t.check("ts guard lists the files once per run", ts_guard.count("'ls-files'") == 1 and "listed" in ts_guard)
    t.check("go guard skips another checkout (a directory holding .git)",
            "otherCheckout(path)" in starters["go"][0].read_text(encoding="utf-8"))
    t.check("rust guard skips another checkout (a directory holding .git)",
            'path.join(".git").exists()' in starters["rust"][0].read_text(encoding="utf-8"))
    t.check("dotnet guard skips another checkout (a directory holding .git)",
            "IsOtherCheckout(sub)" in starters["dotnet"][0].read_text(encoding="utf-8"))
    hook = (shared / ".githooks/pre-push").read_text(encoding="utf-8")
    t.check("pre-push is a POSIX sh script", hook.startswith("#!/bin/sh"))
    # a Windows checkout must not turn the hook or the scripts into CRLF (sh: not found)
    rels = [(shared / ".githooks/pre-push"), (shared / "scripts/delivery/agent_setup.sh"),
            (shared / "scripts/delivery/branch_gate.py"), (shared / "scripts/delivery/gate.json")]
    attr = run(["git", "check-attr", "eol", "--", *[r.as_posix() for r in rels]], cwd=shared)
    lines = [l for l in attr.out.splitlines() if l.strip()]
    t.check("git attributes pin LF for the hook and the delivery scripts",
            attr.code == 0 and len(lines) == len(rels) and all(l.endswith(": lf") for l in lines), attr.out + attr.err)


def sc_packages(t: T, shared: Path) -> None:
    def tree(files: dict) -> Path:
        root = Path(tempfile.mkdtemp(dir=_TMP_ROOT))
        for rel, text in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return root

    # pnpm-workspace
    yaml = "# comment\npackages:\n  # apps\n  - 'apps/*'\n  - \"packages/**\"  # libs\n  - '!packages/skip'\nother:\n  - 'nope/*'\n"
    t.eq("pnpm yaml: block list, quotes, comments, negation, other keys",
         dc.parse_pnpm_patterns(yaml), ["apps/*", "packages/**", "!packages/skip"])
    t.eq("pnpm yaml: flow list", dc.parse_pnpm_patterns("packages: ['a/*', \"b\"]\n"), ["a/*", "b"])
    t.eq("pnpm yaml: unindented list items", dc.parse_pnpm_patterns("packages:\n- a/*\n- b/*\nx: 1\n"), ["a/*", "b/*"])
    root = tree({"pnpm-workspace.yaml": yaml, "apps/web/x": "", "apps/api/x": "", "packages/ui/x": "",
                 "packages/skip/x": "", "packages/deep/inner/x": "", "nope/q/x": "", "apps/web/node_modules/m/x": ""})
    got = dc.discover_packages(root, {"kind": "pnpm-workspace"})
    t.eq("pnpm packages: globs expanded, negation applied, node_modules ignored",
         got, ["apps/api", "apps/web", "packages/deep", "packages/deep/inner", "packages/ui"])
    try:
        dc.discover_packages(tree({"x": ""}), {"kind": "pnpm-workspace"})
        t.check("pnpm packages: missing pnpm-workspace.yaml is an error", False)
    except dc.DeliveryError:
        t.check("pnpm packages: missing pnpm-workspace.yaml is an error", True)

    # cargo-workspace
    cargo = '[workspace]\nmembers = ["crates/*", "tools/cli"]\nexclude = ["crates/old"]\n'
    root = tree({"Cargo.toml": cargo, "crates/a/Cargo.toml": "", "crates/b/Cargo.toml": "",
                 "crates/old/Cargo.toml": "", "crates/notacrate/readme": "", "tools/cli/Cargo.toml": ""})
    t.eq("cargo packages: member globs, exclude, dirs without Cargo.toml dropped",
         dc.discover_packages(root, {"kind": "cargo-workspace"}), ["crates/a", "crates/b", "tools/cli"])
    root = tree({"Cargo.toml": '[package]\nname = "x"\n[workspace]\nmembers = ["crates/*"]\n', "crates/a/Cargo.toml": ""})
    t.eq("cargo packages: a root package is '.'",
         dc.discover_packages(root, {"kind": "cargo-workspace"}), [".", "crates/a"])
    root = tree({"Cargo.toml": '[package]\nname = "solo"\n'})
    t.eq("cargo packages: a single crate", dc.discover_packages(root, {"kind": "cargo-workspace"}), ["."])

    # go-modules
    root = tree({"go.mod": "module a\n", "svc/x/go.mod": "module b\n", "svc/x/internal/y.go": "",
                 "vendor/z/go.mod": "", "node_modules/q/go.mod": "", "plain/main.go": ""})
    t.eq("go packages: dirs holding go.mod, vendor and node_modules skipped",
         dc.discover_packages(root, {"kind": "go-modules"}), [".", "svc/x"])

    # dotnet-sln
    sln = ('Microsoft Visual Studio Solution File, Format Version 12.00\n'
           'Project("{FAE04EC0-301F-4C32-8D93-1A3956D46DE8}") = "Api", "src\\Api\\Api.csproj", "{11111111-1111-1111-1111-111111111111}"\nEndProject\n'
           'Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "src", "src", "{22222222-2222-2222-2222-222222222222}"\nEndProject\n'
           'Project("{FAE04EC0-301F-4C32-8D93-1A3956D46DE8}") = "Core", "src/Core/Core.csproj", "{33333333-3333-3333-3333-333333333333}"\nEndProject\n'
           'Project("{FAE04EC0-301F-4C32-8D93-1A3956D46DE8}") = "T", "tests\\T.Tests\\T.Tests.fsproj", "{44444444-4444-4444-4444-444444444444}"\nEndProject\n')
    root = tree({"app.sln": sln})
    t.eq("dotnet packages: project dirs, solution folders ignored, both slash styles",
         dc.discover_packages(root, {"kind": "dotnet-sln"}), ["src/Api", "src/Core", "tests/T.Tests"])
    t.eq("dotnet packages: .slnx",
         dc.discover_packages(tree({"a.slnx": '<Solution><Project Path="src/A/A.csproj" /></Solution>'}),
                              {"kind": "dotnet-sln"}), ["src/A"])

    # mapping files to packages, and widening rules
    pk = ["apps/web", "apps/web/inner", "packages/ui"]
    t.eq("package_of: the deepest package wins", dc.package_of("apps/web/inner/a.ts", pk), "apps/web/inner")
    t.eq("package_of: a sibling prefix is not a match", dc.package_of("apps/webby/a.ts", pk), None)
    t.eq("package_of: the root package catches the rest", dc.package_of("README.md", [".", "x"]), ".")
    t.eq("package_of: nested beats root", dc.package_of("x/a", [".", "x"]), "x")
    t.eq("widen: exact root file", (dc.widen_match("pnpm-lock.yaml", "pnpm-lock.yaml"),
                                    dc.widen_match("apps/web/pnpm-lock.yaml", "pnpm-lock.yaml")), (True, False))
    t.eq("widen: directory prefix", (dc.widen_match(".github/workflows/ci.yml", ".github/"),
                                     dc.widen_match("x.github/a", ".github/")), (True, False))
    t.eq("widen: glob reaches nested lockfiles", (dc.widen_match("src/A/packages.lock.json", "*packages.lock.json"),
                                                  dc.widen_match("src/A/other.json", "*packages.lock.json")), (True, False))


# --------------------------------------------------------------------------
# scenarios: DL1 (inert paths keep results valid) and DL4 (narrower valves)
# --------------------------------------------------------------------------

def sc_inert_base(t: T, shared: Path) -> None:
    """DL1: a result stays valid when the base moved only by commits under inert_paths."""
    box = Box(shared)
    box.gated("feat/ok", {"apps/web/ok.txt": "ok\n"})
    box.gated("feat/failing", {"apps/web/f.txt": "f\n"}, fail="unit")
    box.g("checkout", "-q", "main")
    box.commit({"docs/a.txt": "a\n"}, "docs one")
    box.commit({"docs/artifacts/b.txt": "b\n"}, "docs two")
    box.g("push", "-q", "origin", "main")

    r = verify(box, "feat/ok")
    t.eq("base moved by docs only: trusted", r.code, 0)
    t.has("... and says why", r.out, "base moved only by inert commits: 2")
    r = verify(box, "feat/ok", "--json")
    t.eq("... the verdict carries the count", json.loads(r.out)["inert_commits"], 2)
    r = verify(box, "feat/ok", "--strict-base")
    t.eq("--strict-base: the same move is stale", r.code, 1)
    t.has("--strict-base: says stale base", r.out, "stale base")
    r = verify(box, "feat/failing")
    t.eq("an inert move does not excuse a failing result", r.code, 1)
    r = verify(box, "feat/ok", "--allow-older-base")
    t.eq("--allow-older-base still accepts an ancestor base", r.code, 0)
    t.has("--allow-older-base keeps its own message", r.out, "older base")

    # a merge commit counts by its diff
    box.g("checkout", "-q", "-B", "docs-side", "main")
    box.commit({"docs/side.txt": "s\n"}, "docs side")
    box.g("checkout", "-q", "main")
    box.g("merge", "-q", "--no-ff", "-m", "merge docs", "docs-side")
    box.g("push", "-q", "origin", "main")
    r = verify(box, "feat/ok")
    t.eq("a docs-only merge commit keeps it trusted", r.code, 0)
    t.has("... counted", r.out, "base moved only by inert commits: 4")

    # one code commit among the docs commits: stale
    box.commit({"apps/api/code.txt": "c\n"}, "code lands")
    box.g("push", "-q", "origin", "main")
    r = verify(box, "feat/ok")
    t.eq("one non-inert change in the range: stale", r.code, 1)
    t.has("... says stale base", r.out, "stale base")

    # an ancestor is required: a rewound base that differs only in docs
    box.g("checkout", "-q", "-B", "alt", box.main_sha + "~1")
    box.commit({"docs/other.txt": "o\n"}, "docs on another line")
    box.g("push", "-q", "--force", "origin", "alt:main")
    r = verify(box, "feat/ok")
    t.eq("a base that is not an ancestor is stale even when only docs differ", r.code, 1)

    # a gate.json can name its own inert paths; the default is docs/**
    cfg = Box.gate_json()
    cfg["inert_paths"] = ["notes/**"]
    nb = Box(shared, gate_json=cfg)
    nb.gated("feat/ok", {"apps/web/ok.txt": "ok\n"})
    nb.g("checkout", "-q", "main")
    nb.commit({"docs/a.txt": "a\n"}, "docs")
    nb.g("push", "-q", "origin", "main")
    t.eq("inert_paths replaces the default: docs is no longer inert", verify(nb, "feat/ok").code, 1)
    nb.commit({"notes/n.txt": "n\n"}, "notes")
    nb.g("reset", "-q", "--hard", "HEAD~2")
    nb.commit({"notes/n.txt": "n\n"}, "notes")
    nb.g("push", "-q", "--force", "origin", "main")
    r = verify(nb, "feat/ok")
    t.eq("... and a listed path is", r.code, 0)
    t.has("... counted", r.out, "base moved only by inert commits: 1")

    for bad in ("x", [1], {"a": "b"}):
        cfg = Box.gate_json()
        cfg["inert_paths"] = bad
        b = Box(shared, gate_json=cfg)
        b.branch("feat/e", {"apps/web/a.txt": "a\n"})
        t.eq("inert_paths %r is a configuration error" % (bad,), b.gate("--no-publish").code, 2)
    cfg = Box.gate_json()
    cfg["lockfile_scope"] = "everything"
    b = Box(shared, gate_json=cfg)
    b.branch("feat/e", {"apps/web/a.txt": "a\n"})
    t.eq("an unknown lockfile_scope is a configuration error", b.gate("--no-publish").code, 2)


PNPM_LOCK_HEAD = "lockfileVersion: '9.0'\n\nimporters:\n\n"


def pnpm_lock(root: str = "2.0.0", api: str = "1.0.0", core: str = "1.0.0", ui: str = "1.0.0",
              snap: str = "a") -> str:
    def imp(path: str, dep: str, ver: str) -> str:
        return "  %s:\n    dependencies:\n      %s:\n        specifier: '1'\n        version: %s\n\n" % (path, dep, ver)

    return (PNPM_LOCK_HEAD + imp(".", "turbo", root) + imp("apps/api", "left-pad", api)
            + imp("packages/core", "is-odd", core) + imp("packages/ui", "clsx", ui)
            + "packages:\n\n  left-pad@1.0.0:\n    resolution: {integrity: %s}\n" % snap)


class LockBox(Box):
    INIT_FILES = {
        **Box.INIT_FILES,
        "pnpm-lock.yaml": pnpm_lock(),
        "packages/core/package.json": '{"name": "@x/core"}\n',
        "packages/ui/package.json": '{"name": "@x/ui", "dependencies": {"@x/core": "workspace:*"}}\n',
        "apps/web/package.json": '{"name": "@x/web", "dependencies": {"@x/ui": "workspace:*"}}\n',
        "apps/api/package.json": '{"name": "@x/api"}\n',
    }

    @classmethod
    def gate_json(cls) -> dict:
        cfg = Box.gate_json()
        cfg["widen_on"] = [e for e in cfg["widen_on"] if e != "pnpm-lock.yaml"]
        cfg["lockfile_scope"] = "pnpm-importers"
        for s in cfg["steps"]:
            if s["name"] == "unit":
                s["scope"] = "changed+dependents"
                s["run"] = cls.step_cmd("unit", "{affected_dirs}")
        return cfg


def sc_lockfile_scope(t: T, shared: Path) -> None:
    """DL4: a lockfile change widens only when it cannot be pinned to a package."""
    box = LockBox(shared)

    def lock(label: str, **kw):
        box.branch("feat/lock", {"pnpm-lock.yaml": pnpm_lock(**kw)})
        box.clear_log()
        r = box.gate("--no-publish")
        res = box.result()
        return r, res, [x for x in box.ran() if x[0] == "unit"]

    r, res, unit = lock("api importer", api="1.0.1", snap="b")
    t.eq("one importer's dependencies changed: exit 0, not widened", (r.code, res["widened"]), (0, False))
    t.eq("... that package is the changed set", res["changed_dirs"], ["apps/api"])
    t.eq("... and the steps run scoped", unit, [["unit", "apps/api"]])

    r, res, unit = lock("core importer", core="1.0.1")
    t.eq("a leaf package's importer: its dependents are affected", unit,
         [["unit", "apps/web", "packages/core", "packages/ui"]])
    t.eq("... and it is not widened", res["widened"], False)

    r, res, unit = lock("root importer", root="2.0.1")
    t.eq("the root importer changed: widened", (res["widened"], unit), (True, [["unit", "FULL"]]))

    r, res, unit = lock("transitive", snap="c")
    t.eq("a change outside every importer cannot be pinned: widened", (res["widened"], unit),
         (True, [["unit", "FULL"]]))

    r, res, unit = lock("ui importer", ui="1.0.1")
    outcomes = {s["name"]: s["outcome"] for s in res["steps"]}
    t.eq("a ui package's importer counts as a ui change: e2e runs", outcomes["e2e"], "pass")

    # an old gate.json keeps the lockfile in widen_on: it still widens
    cfg = LockBox.gate_json()
    cfg["widen_on"].append("pnpm-lock.yaml")
    old = LockBox(shared, gate_json=cfg)
    old.branch("feat/lock", {"pnpm-lock.yaml": pnpm_lock(api="1.0.1")})
    old.gate("--no-publish")
    t.eq("lockfile in widen_on: widens whatever lockfile_scope says", old.result()["widened"], True)

    # no lockfile_scope: as before
    plain = LockBox(shared, gate_json={**LockBox.gate_json(), "lockfile_scope": "widen"})
    plain.branch("feat/lock", {"pnpm-lock.yaml": pnpm_lock(api="1.0.1")})
    plain.gate("--no-publish")
    t.eq("lockfile_scope widen: the lockfile is only a widen_on entry, so it does not widen",
         plain.result()["widened"], False)

    # per-package lockfiles (Go modules, .NET projects): the package's own file
    class GoBox(Box):
        INIT_FILES = {**{k: v for k, v in Box.INIT_FILES.items() if k != "pnpm-workspace.yaml"},
                      "svc/a/go.mod": "module a\n", "svc/a/go.sum": "s\n", "svc/b/go.mod": "module b\n"}

        @classmethod
        def gate_json(cls) -> dict:
            cfg = Box.gate_json()
            cfg["packages"] = {"kind": "go-modules"}
            cfg["widen_on"] = ["go.work", "scripts/delivery/"]
            cfg["lockfile_scope"] = "per-package"
            return cfg

    gb = GoBox(shared)
    gb.branch("feat/sum", {"svc/a/go.sum": "t\n"})
    gb.gate("--no-publish")
    res = gb.result()
    t.eq("a module's go.sum: that module only, not widened", (res["changed_dirs"], res["widened"]), (["svc/a"], False))
    gb.branch("feat/work", {"go.work": "w\n"})
    gb.gate("--no-publish")
    t.eq("go.work still widens", gb.result()["widened"], True)

    # the shipped tracks
    for track, widening, scope in (("ts", "pnpm-lock.yaml", "pnpm-importers"), ("go", "go.sum", "per-package"),
                                   ("dotnet", "packages.lock.json", "per-package"), ("rust", None, "widen")):
        cfg = json.loads((TOOLING / track / "scripts/delivery/gate.json").read_text(encoding="utf-8"))
        t.eq("%s gate.json: lockfile_scope" % track, cfg.get("lockfile_scope"), scope)
        t.eq("%s gate.json: inert_paths" % track, cfg.get("inert_paths"), ["docs/**"])
        listed = [e for e in cfg["widen_on"] if "lock" in e or "go.sum" in e or e == "go.mod"]
        t.eq("%s gate.json: lockfiles in widen_on" % track, listed, ["Cargo.lock"] if track == "rust" else [])


class GraphBox(Box):
    """A workspace with a dependency graph and end-to-end spec directories."""

    INIT_FILES = {
        **Box.INIT_FILES,
        "packages/core/package.json": '{"name": "@x/core"}\n',
        "packages/ui/package.json": '{"name": "@x/ui", "dependencies": {"@x/core": "workspace:*"}}\n',
        "apps/web/package.json": '{"name": "@x/web", "dependencies": {"@x/ui": "workspace:*"}}\n',
        "apps/admin/package.json": '{"name": "@x/admin"}\n',
        "apps/api/package.json": '{"name": "@x/api"}\n',
        "apps/web/e2e/web.spec.txt": "web\n",
        "e2e/ui/ui.spec.txt": "ui\n",
    }

    @classmethod
    def gate_json(cls) -> dict:
        cfg = e2e_gate_json(with_map=False)
        cfg["ui_paths"] = ["apps/web/", "apps/admin/", "packages/ui/", "shared-ui/"]
        return cfg


def sc_e2e_graph(t: T, shared: Path) -> None:
    """DL4: without an e2e_map the specs come from the workspace dependency graph."""
    box = GraphBox(shared)

    def e2e(files: dict, *args: str, b: Box | None = None):
        b = b or box
        b.branch("feat/e", files)
        b.clear_log()
        r = b.gate("--no-publish", *args)
        entry = {s["name"]: s for s in b.result()["steps"]}["e2e"]
        return r, [x for x in b.ran() if x[0] == "e2e"], entry

    r, ran, entry = e2e({"packages/ui/a.txt": "a\n"})
    t.eq("a shared ui package: its own specs and its dependents' specs", ran,
         [["e2e", "apps/web/e2e", "e2e/ui"]])
    t.eq("... recorded as affected", (entry.get("selection"), entry.get("specs")),
         ("affected", ["apps/web/e2e", "e2e/ui"]))

    r, ran, entry = e2e({"apps/web/a.txt": "a\n"})
    t.eq("an app's change: only that app's specs (the package it imports is not affected)", ran,
         [["e2e", "apps/web/e2e"]])

    r, ran, entry = e2e({"apps/admin/a.txt": "a\n"})
    t.eq("a ui package with no specs and no dependents: the whole suite", (ran, entry.get("selection")),
         ([["e2e"]], "full"))

    r, ran, entry = e2e({"apps/web/a.txt": "a\n", "apps/admin/a.txt": "a\n"})
    t.eq("one changed ui package uncovered: the whole suite, not just the covered one", ran, [["e2e"]])

    r, ran, entry = e2e({"packages/ui/a.txt": "a\n", "package.json": "{\"x\": 1}\n"})
    t.eq("a widened gate: run_full", ran, [["e2e", "FULL"]])

    r, ran, entry = e2e({"packages/ui/a.txt": "a\n"}, "--full")
    t.eq("--full: run_full", ran, [["e2e", "FULL"]])

    # a shared package without specs of its own is covered by a dependent that has them
    class NoUiSpecs(GraphBox):
        INIT_FILES = {k: v for k, v in GraphBox.INIT_FILES.items() if not k.startswith("e2e/")}

    nb = NoUiSpecs(shared)
    r, ran, entry = e2e({"packages/ui/a.txt": "a\n"}, b=nb)
    t.eq("... a shared package with no specs of its own runs its dependents' specs", ran,
         [["e2e", "apps/web/e2e"]])

    r, ran, entry = e2e({"apps/web/a.txt": "a\n", "shared-ui/x.txt": "x\n"})
    t.eq("a ui file outside any package: the specs cannot be known, the whole suite", ran, [["e2e"]])

    # the map wins when there is one
    mapped = GraphBox(shared, gate_json={**GraphBox.gate_json(),
                                         "e2e_map": {"specs": [{"spec": "e2e/only.spec.txt", "paths": ["packages/ui/"]}],
                                                     "full_on": []}})
    r, ran, entry = e2e({"packages/ui/a.txt": "a\n"}, b=mapped)
    t.eq("e2e_map present: it wins over the graph", ran, [["e2e", "e2e/only.spec.txt"]])


# --------------------------------------------------------------------------
# scenarios: quick join check, train freeze, runner health (DL2, DL6, DL7)
# --------------------------------------------------------------------------

# The two scripts of DL6 and DL7 are copied into every box.
for _name in ("runner_health.py", "train_freeze.py"):
    if _name not in SCRIPT_FILES:
        SCRIPT_FILES.append(_name)

# A `gh` that answers from a JSON fixture (GH_STUB_FIXTURE) and logs its calls.
GH_STUB = r'''
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\n")
fx = json.load(open(os.environ["GH_STUB_FIXTURE"], encoding="utf-8"))
def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)
if argv[:2] == ["pr", "list"]:
    if fx.get("pr_error"):
        fail("HTTP 502: bad gateway")
    head = argv[argv.index("--head") + 1] if "--head" in argv else None
    state = argv[argv.index("--state") + 1] if "--state" in argv else None
    rows = [p for p in fx.get("prs", []) if head in (None, p["headRefName"]) and state in (None, "all", p["state"])]
    print(json.dumps([{k: v for k, v in p.items() if k not in ("headRefName", "state")} for p in rows]))
elif argv[:2] == ["run", "list"]:
    print(json.dumps(fx.get("runs", [])))
elif argv[:1] == ["api"]:
    if fx.get("runners_error"):
        fail("HTTP 403: Must have admin rights to Repository.")
    print(json.dumps({"runners": fx.get("runners", [])}))
elif argv[:2] == ["variable", "get"]:
    v = fx.get("vars", {}).get(argv[2])
    if v is None:
        fail("could not find variable")
    print(v)
else:
    fail("stub gh: unexpected call " + " ".join(argv))
'''


class GhStub:
    """A stub `gh` first on PATH for the scripts a test runs."""

    def __init__(self, box: Box, fixture: dict):
        self.dir = box.root / "ghbin"
        self.dir.mkdir(exist_ok=True)
        (self.dir / "gh.py").write_text(GH_STUB, encoding="utf-8")
        if os.name == "nt":
            (self.dir / "gh.cmd").write_text('@"%s" "%%~dp0gh.py" %%*\r\n' % sys.executable, encoding="utf-8")
        else:
            shim = self.dir / "gh"
            shim.write_text('#!/bin/sh\nexec "%s" "$(dirname "$0")/gh.py" "$@"\n' % sys.executable, encoding="utf-8")
            shim.chmod(0o755)
        self.fixture = self.dir / "fixture.json"
        self.log = self.dir / "gh.log"
        self.set(fixture)

    def set(self, fixture: dict) -> None:
        self.fixture.write_text(json.dumps(fixture), encoding="utf-8")
        if self.log.exists():
            self.log.unlink()

    def calls(self) -> list:
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x]

    def env(self, extra: dict | None = None) -> dict:
        env = {"PATH": str(self.dir) + os.pathsep + os.environ.get("PATH", ""),
               "GH_STUB_FIXTURE": str(self.fixture), "GH_STUB_LOG": str(self.log)}
        env.update(extra or {})
        return env


def ws_box(shared: Path, gate_json: dict | None = None) -> Box:
    """An integration box whose packages depend on each other: web -> ui -> core, api -> core."""

    class WsBox(Box):
        INIT_FILES = {
            **Box.INIT_FILES,
            "packages/core/package.json": '{"name": "@x/core"}\n',
            "packages/ui/package.json": '{"name": "@x/ui", "dependencies": {"@x/core": "workspace:*"}}\n',
            "apps/web/package.json": '{"name": "@x/web", "devDependencies": {"@x/ui": "workspace:*"}}\n',
            "apps/api/package.json": '{"name": "@x/api"}\n',
        }

    box = WsBox(shared, gate_json=gate_json)
    box.g("checkout", "-q", "-B", "integ", "main")
    box.push("integ")
    return box


def sc_join_quick(t: T, shared: Path) -> None:
    """DV493: the join is light: setup, typecheck and lint of the packages the merges touched, then the
    fast guards; never a test step, never a full gate; it records the time of each step."""
    box = ws_box(shared)
    box.gated("feat/core", {"packages/core/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/api", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/core", "feat/api", "--push")
    t.eq("two branches joined: exit 0", r.code, 0)
    t.eq("the light check runs the install, typecheck, lint and the fast guards (no unit, e2e)",
         [x[0] for x in box.ran(True)], ["setup", "typecheck", "lint", "guards", "secret-scan"])
    touched = ["apps/api", "packages/core"]
    t.eq("typecheck gets the packages the merges touched", [x for x in box.ran() if x[0] == "typecheck"],
         [["typecheck"] + touched])
    t.eq("... lint too", [x for x in box.ran() if x[0] == "lint"], [["lint"] + touched])
    t.eq("no test step ran", [x for x in box.ran() if x[0] == "unit"], [])
    jr = join_result(box)
    qc = jr.get("quick_check", {})
    t.eq("join-result.json records the check", (qc.get("pass"), qc.get("changed_dirs")), (True, touched))
    t.eq("... with a time per step", [(s["name"], isinstance(s["seconds"], float)) for s in qc.get("steps", [])],
         [("setup", True), ("typecheck", True), ("lint", True), ("fast-guards", True)])
    t.check("... and a total", isinstance(qc.get("seconds"), float))
    t.has("stdout lists the time of each step", r.out, "typecheck ")
    t.has("... and the total", r.out, "light check passed in")
    t.eq("it is not a gate: no result is published for the integration branch",
         box.remote_ref("refs/gate-results/integ"), None)
    t.eq("... and the integration branch was pushed", box.g("rev-parse", "origin/integ"), box.g("rev-parse", "HEAD"))

    # a failing typecheck, lint or guard stops the join before the push; a failing test is CI's
    for failing in ("typecheck", "lint", "guards"):
        box = ws_box(shared)
        box.gated("feat/core", {"packages/core/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
        box.gated("feat/api", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
        before = box.g("rev-parse", "origin/integ")
        r = join(box, "--into", "integ", "feat/core", "feat/api", "--push", env={"GATE_TEST_FAIL": failing})
        t.eq("a failing %s: exit 1" % failing, r.code, 1)
        t.eq("... nothing pushed", box.g("rev-parse", "origin/integ"), before)
        t.eq("... and the failure is recorded", join_result(box).get("quick_check", {}).get("pass"), False)

    box = ws_box(shared)
    box.gated("feat/core", {"packages/core/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/api", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    r = join(box, "--into", "integ", "feat/core", "feat/api", env={"GATE_TEST_FAIL": "unit,e2e"})
    t.eq("unit and e2e are not part of the light check", r.code, 0)

    # per project: join_guards false drops the guards; "join": true on a step adds it
    cfg = Box.gate_json()
    cfg["join_guards"] = False
    for st in cfg["steps"]:
        if st["name"] == "lint":
            st["join"] = False
        if st["name"] == "unit":
            st["join"] = True
    box = ws_box(shared, gate_json=cfg)
    box.gated("feat/core", {"packages/core/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/api", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/core", "feat/api")
    t.eq("configured: no guards, no lint, unit added", (r.code, [x[0] for x in box.ran(True)]),
         (0, ["setup", "typecheck", "unit"]))

    # nothing but docs changed: install and the guards only, and it passes
    box = ws_box(shared)
    box.gated("feat/docs", {"docs/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/docs2", {"docs/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/docs", "feat/docs2")
    t.eq("no package changed: exit 0, the install and the guards ran",
         (r.code, [x[0] for x in box.ran(True)]), (0, ["setup", "guards", "secret-scan"]))

    # a widening file (the lockfile) runs the full commands of the light steps, still no tests
    box = ws_box(shared)
    box.gated("feat/lock", {"pnpm-lock.yaml": "lock\nl1\nchanged\n"}, frm="integ", base_ref="origin/integ")
    box.gated("feat/api", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/lock", "feat/api")
    t.eq("a widened join runs the full typecheck, and no tests",
         ([x for x in box.ran() if x[0] == "typecheck"], [x for x in box.ran() if x[0] == "unit"]),
         ([["typecheck", "FULL"]], []))

    # --no-gate and the trusted-tree skip stay
    box = ws_box(shared)
    box.gated("feat/api", {"apps/api/b.txt": "b\n"}, frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/api", "--no-gate")
    t.eq("--no-gate: no check", (r.code, box.ran(True), "quick_check" in join_result(box)), (0, [], False))
    box = ws_box(shared)
    box.gated("feat/api", {"apps/api/b.txt": "b\n"}, base_ref="origin/main", frm="integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/api")
    t.eq("a joined tree equal to a trusted branch head: the check is skipped, and says so",
         (r.code, box.ran(True), "gate on the joined head skipped" in r.out), (0, [], True))


def hook_box(shared: Path, fixture: dict) -> tuple[Box, GhStub]:
    box = Box(shared)
    box.g("config", "core.hooksPath", ".githooks")
    stub = GhStub(box, fixture)
    box.branch("train", {"apps/web/a.txt": "a\n"})
    return box, stub


def push(box: Box, stub: GhStub, *args: str, env: dict | None = None) -> R:
    return run(["git", "push", "-q", *args], cwd=box.work, extra_env=stub.env(env))


def sc_freeze(t: T, shared: Path) -> None:
    """DL6: no push to a branch whose ready PR is being tested."""
    ready = {"number": 12, "isDraft": False, "url": "https://example.test/pr/12", "headRefOid": "b" * 40,
             "headRefName": "train", "state": "open"}
    running = {"databaseId": 9001, "workflowName": "ci", "status": "in_progress", "conclusion": ""}
    done = {"databaseId": 9001, "workflowName": "ci", "status": "completed", "conclusion": "failure"}

    box, stub = hook_box(shared, {"prs": [], "runs": []})
    r = push(box, stub, "-u", "origin", "train")
    t.eq("no pull request: the push is allowed", r.code, 0)
    t.eq("... with one gh call (the hook stays fast)", [c[:2] for c in stub.calls()], [["pr", "list"]])
    t.check("... and the branch arrived", box.remote_ref("refs/heads/train") is not None)
    tip = box.g("rev-parse", "HEAD")

    def next_commit(n: str) -> None:
        box.commit({"apps/web/%s.txt" % n: n + "\n"}, "more " + n)

    stub.set({"prs": [ready], "runs": [running]})
    next_commit("b")
    r = push(box, stub, "origin", "train")
    t.check("a ready PR whose CI is running: the push is refused", r.code != 0, r.text)
    t.has("... naming the pull request", r.text, "#12")
    t.has("... and the run", r.text, "9001")
    t.eq("... the remote did not move", box.remote_ref("refs/heads/train"), tip)
    t.eq("... two gh calls at most", [c[:2] for c in stub.calls()], [["pr", "list"], ["run", "list"]])
    t.has("... and the hint names the override", r.text, "DELIVERY_FREEZE_OVERRIDE=1")

    r = push(box, stub, "origin", "train", env={"DELIVERY_FREEZE_OVERRIDE": "1"})
    t.eq("DELIVERY_FREEZE_OVERRIDE=1: the push goes through", r.code, 0)
    t.has("... and says the running CI will restart", r.text, "will restart")
    t.eq("... the remote moved", box.remote_ref("refs/heads/train"), box.g("rev-parse", "HEAD"))

    stub.set({"prs": [ready], "runs": [done]})
    next_commit("c")
    r = push(box, stub, "origin", "train")
    t.eq("CI finished, failed: the push is allowed (fix forward)", r.code, 0)
    stub.set({"prs": [ready], "runs": [{**done, "conclusion": "success"}]})
    next_commit("d")
    t.eq("CI finished, passed: allowed", push(box, stub, "origin", "train").code, 0)

    stub.set({"prs": [{**ready, "isDraft": True}], "runs": [running]})
    next_commit("e")
    t.eq("a draft PR: allowed", push(box, stub, "origin", "train").code, 0)

    stub.set({"prs": [{**ready, "state": "closed"}], "runs": [running]})
    next_commit("f")
    t.eq("the ready PR was closed unmerged (train abandoned): allowed", push(box, stub, "origin", "train").code, 0)

    stub.set({"prs": [ready], "runs": [], "pr_error": True})
    next_commit("g")
    r = push(box, stub, "origin", "train")
    t.eq("GitHub unreachable: allowed", r.code, 0)
    t.check("... with a warning", "warning" in r.text and "allowing the push" in r.text, r.text)

    stub.set({"prs": [ready], "runs": []})
    next_commit("h")
    t.eq("a ready PR with no run listed yet: allowed", push(box, stub, "origin", "train").code, 0)

    # a run of another commit does not matter: the query is for the PR's head commit
    stub.set({"prs": [ready], "runs": [running]})
    next_commit("i")
    push(box, stub, "origin", "train")
    t.eq("the run list is asked for the PR's head commit",
         [c for c in stub.calls() if c[:2] == ["run", "list"]][0][2:4], ["--commit", "b" * 40])

    # pushing tags skips the freeze
    stub.set({"prs": [ready], "runs": [running]})
    box.g("tag", "v1")
    r = push(box, stub, "origin", "v1")
    t.eq("a tag push does not ask GitHub", (r.code, stub.calls()), (0, []))


def runner_fixture(box: Box, files: dict) -> None:
    box.g("checkout", "-q", "integ")
    for name, text in files.items():
        box.write(".github/workflows/" + name, text)
    box.g("add", "-A")
    box.g("commit", "-q", "-m", "workflows")
    box.g("push", "-q", "origin", "integ")


WF_VAR = ("name: ci\non: push\njobs:\n  build:\n    runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '\"ubuntu-latest\"') }}\n"
          "    steps:\n      - run: echo hi\n")


def sc_runner_health(t: T, shared: Path) -> None:
    """DL7: join warns, never blocks, when no online runner carries a self-hosted label set."""
    selfhosted = {"CI_RUNS_ON": '["self-hosted","gpu"]'}
    online = {"status": "online", "labels": [{"name": "self-hosted"}, {"name": "linux"}]}
    gpu = {"status": "online", "labels": [{"name": "self-hosted"}, {"name": "gpu"}]}

    def run_join(fixture: dict, wf: dict | None = None):
        box = integ_box(shared)
        box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
        runner_fixture(box, wf or {"ci.yml": WF_VAR})
        stub = GhStub(box, fixture)
        r = join(box, "--into", "integ", "feat/a", "--no-gate", env=stub.env())
        return r, box, stub

    r, box, stub = run_join({"vars": selfhosted, "runners": [online]})
    t.eq("no online runner with the label: join still succeeds (warnings only)", r.code, 0)
    t.check("... and warns, naming the label", "WARNING" in r.out and "gpu" in r.out, r.out)
    t.eq("... the report says warn", join_result(box)["runner_health"]["status"], "warn")

    r, box, stub = run_join({"vars": selfhosted, "runners": [online, gpu]})
    t.check("an online runner carries every label: no warning", "WARNING" not in r.out and "runner health: ok" in r.out, r.out)

    r, box, stub = run_join({"vars": selfhosted, "runners": [{**gpu, "status": "offline"}]})
    t.check("the only runner with the label is offline: warning", "WARNING" in r.out, r.out)

    r, box, stub = run_join({"vars": {}, "runners": []})
    t.check("the variable unset: the default is ubuntu-latest, hosted, no warning and no runner list",
            "WARNING" not in r.out and not [c for c in stub.calls() if c[0] == "api"], r.out)

    wf_hosted = {"ci.yml": "jobs:\n  a:\n    runs-on: windows-2022\n  b:\n    runs-on: [macos-14]\n"
                           "  c:\n    runs-on:\n      - ubuntu-24.04\n"}
    r, box, stub = run_join({"runners": []}, wf_hosted)
    t.check("standard hosted labels count as available",
            "WARNING" not in r.out and not [c for c in stub.calls() if c[0] == "api"], r.out)

    wf_self = {"ci.yml": "jobs:\n  a:\n    runs-on: [self-hosted, linux, arm64]\n"}
    wf_block = {"ci.yml": "jobs:\n  a:\n    runs-on:\n      - self-hosted\n      - arm64\n    steps: []\n"}
    r, box, stub = run_join({"runners": [online]}, wf_block)
    t.check("a block list of labels is read", "WARNING" in r.out and "arm64" in r.out, r.out)
    r, box, stub = run_join({"runners": [online]}, wf_self)
    t.check("a literal self-hosted label list is checked too", "WARNING" in r.out and "arm64" in r.out, r.out)
    r, box, stub = run_join({"runners": [{**online, "labels": online["labels"] + [{"name": "arm64"}]}]}, wf_self)
    t.check("... and passes when one runner has all three", "WARNING" not in r.out, r.out)

    r, box, stub = run_join({"vars": selfhosted, "runners_error": True})
    t.eq("runners cannot be listed: join succeeds", r.code, 0)
    t.check("... and says the check was skipped and why", "check skipped" in r.out and "admin" in r.out, r.out)
    t.eq("... the report says skipped", join_result(box)["runner_health"]["status"], "skipped")


# --------------------------------------------------------------------------
# mutation pass
# --------------------------------------------------------------------------

# (id, file relative to shared/, text to replace, replacement, scenario that must notice)
MUTANTS = [
    ("verify accepts a UI branch with no e2e record", "scripts/delivery/gate_verify.py",
     '        if needs:\n            reasons.append("no e2e record', '        if False:\n            reasons.append("no e2e record', "e2e_agent"),
    ("verify ignores a failed e2e record", "scripts/delivery/gate_verify.py",
     'if rec.get("required") and rec.get("outcome") != "pass":', 'if False:', "e2e_agent"),
    ("a changed spec file does not count as a UI change", "scripts/delivery/delivery_common.py",
     '    return ui + changed_e2e_specs(ctx.files, ctx.cfg, ctx.root)', '    return ui', "e2e_agent"),
    ("the push check allows any push", "scripts/delivery/e2e_push_check.py",
     '    if not problems:\n        return dc.EXIT_OK', '    if True:\n        return dc.EXIT_OK', "e2e_agent"),
    ("the push check ignores the head", "scripts/delivery/delivery_common.py",
     '    if result.get("head") != head:', '    if False:', "e2e_agent"),
    ("the push check ignores a failed run", "scripts/delivery/delivery_common.py",
     '    if needed and rec.get("outcome") != "pass":', '    if False:', "e2e_agent"),
    ("--e2e-only does not publish", "scripts/delivery/branch_gate.py",
     '    if (not partial or args.e2e_only) and not args.no_publish:', '    if not partial and not args.no_publish:', "e2e_agent"),
    ("the pre-push hook skips the e2e check", ".githooks/pre-push",
     '"$py" scripts/delivery/e2e_push_check.py --commit "$local_sha" $base_args </dev/null || fail=1', ':', "e2e_agent"),
    ("verify accepts a skipped required step", "scripts/delivery/gate_verify.py",
     'elif entry.get("outcome") == "skip" and not str(entry.get("reason") or "").startswith("no "):',
     "elif False:", "required_steps"),
    ("verify accepts a result without a required step", "scripts/delivery/gate_verify.py",
     "if entry is None:", "if False:", "required_steps"),
    ("gate.json may order tests before lint", "scripts/delivery/delivery_common.py",
     "    if req:\n        last = max(", "    if False:\n        last = max(", "required_steps"),
    ("verify ignores a stale head", "scripts/delivery/gate_verify.py",
     'if r_head != verdict["branch_head"]:', "if False:", "verify"),
    ("verify ignores a stale base", "scripts/delivery/gate_verify.py",
     "if r_base != base_head:", "if False:", "verify"),
    ("verify ignores a failing result", "scripts/delivery/gate_verify.py",
     'if result.get("pass") is not True:', "if False:", "verify"),
    ("verify ignores a partial result", "scripts/delivery/gate_verify.py",
     'if result.get("partial"):', "if False:", "verify"),
    ("verify ignores a result for another branch", "scripts/delivery/gate_verify.py",
     'if result.get("branch") != branch:', "if False:", "verify"),
    ("verify accepts any older base", "scripts/delivery/gate_verify.py",
     "if allow_older_base and dc.is_ancestor(r_base, base_head, root):", "if allow_older_base:", "verify"),
    ("gate runs on a dirty tree", "scripts/delivery/branch_gate.py", "    if dirty:", "    if False:", "dirty"),
    ("gate runs changed-scoped steps with no package changed", "scripts/delivery/delivery_common.py",
     "elif not ctx.changed_dirs:", "elif False:", "scopes"),
    ("gate runs e2e whatever changed", "scripts/delivery/delivery_common.py",
     "if not wide and not ui:", "if False:", "scopes"),
    ("affected set ignores dependents", "scripts/delivery/delivery_common.py",
     "if dep not in seen:", "if False:", "affected"),
    ("affected set is the whole workspace for a leaf", "scripts/delivery/delivery_common.py",
     '.replace("{affected_dirs}", " ".join(ctx.packages if wide else ctx.affected_dirs))',
     '.replace("{affected_dirs}", " ".join(ctx.packages))', "affected"),
    ("a step's env is not passed", "scripts/delivery/delivery_common.py",
     "    full_env = {**os.environ, **env} if env else None\n    kw = {}", "    full_env = None\n    kw = {}", "step_env"),
    ("gate never widens", "scripts/delivery/delivery_common.py",
     'reasons = widening_files(files, cfg["widen_on"])', "reasons = []", "widening"),
    ("the gate does not stop at the first failure", "scripts/delivery/delivery_common.py",
     "elif not keep_going:", "elif False:", "failfast"),
    ("--keep-going is ignored", "scripts/delivery/branch_gate.py",
     "keep_going=args.keep_going,", "keep_going=False,", "failfast"),
    ("a failing gate still exits 0", "scripts/delivery/branch_gate.py",
     "exit_code = dc.EXIT_OK if ok else dc.EXIT_TIMEOUT if timed_out else dc.EXIT_FAIL", "exit_code = dc.EXIT_OK", "failures"),
    ("a timed-out gate exits 1", "scripts/delivery/branch_gate.py",
     "dc.EXIT_TIMEOUT if timed_out else dc.EXIT_FAIL", "dc.EXIT_FAIL", "timeout"),
    ("setup does not run", "scripts/delivery/delivery_common.py",
     "    if setup_cmds:\n        if no_setup:", "    if False:\n        if no_setup:", "setup"),
    ("a failed setup does not stop the run", "scripts/delivery/delivery_common.py",
     'halt = "gate timed out" if timed_out else "setup failed"', "halt = None", "setup"),
    ("--no-setup run is not partial", "scripts/delivery/branch_gate.py",
     "partial = only is not None or bool(skip) or args.no_setup", "partial = only is not None or bool(skip)", "setup"),
    ("the stale-lockfile hint is not printed", "scripts/delivery/branch_gate.py",
     'if any(e["name"] == dc.SETUP_STEP and e["outcome"] == "fail" and not timed_out for e in entries):',
     "if False:", "setup"),
    ("a timeout does not kill the process tree", "scripts/delivery/delivery_common.py",
     '    if os.name == "nt":\n        subprocess.run(["taskkill"',
     '    proc.kill()\n    return\n    if os.name == "nt":\n        subprocess.run(["taskkill"', "timeout"),
    ("the time limit is not enforced", "scripts/delivery/delivery_common.py",
     "code = proc.wait(timeout=timeout)", "code = proc.wait()", "timeout"),
    ("--timeout-minutes is ignored", "scripts/delivery/branch_gate.py",
     'minutes = args.timeout_minutes if args.timeout_minutes is not None else cfg["timeout_minutes"]',
     'minutes = cfg["timeout_minutes"]', "timeout"),
    ("gate.json timeout_minutes is ignored", "scripts/delivery/branch_gate.py",
     'else cfg["timeout_minutes"]', "else 30", "timeout"),
    ("a timed-out step is not recorded as failed", "scripts/delivery/delivery_common.py",
     'entry["reason"] = "timed out after %s min" % _minutes(limit_seconds)', 'entry["reason"] = "command failed"', "timeout"),
    ("a timed-out run is not marked timed_out", "scripts/delivery/branch_gate.py",
     '"timed_out": timed_out,', '"timed_out": False,', "timeout"),
    ("step output is not written to the log", "scripts/delivery/delivery_common.py",
     "            log.write(chunk)\n", "            pass\n", "logs"),
    ("step output is not streamed", "scripts/delivery/delivery_common.py",
     "            if echo:\n", "            if False:\n", "logs"),
    ("no FAIL line is printed", "scripts/delivery/delivery_common.py",
     '        if e["outcome"] != "fail":\n            continue\n', "        continue\n", "logs"),
    ("the failure tail is not limited to 40 lines", "scripts/delivery/delivery_common.py",
     "TAIL_LINES = 40", "TAIL_LINES = 400", "logs"),
    ("verify trusts a timed-out result", "scripts/delivery/gate_verify.py",
     'if result.get("timed_out"):', "if False:", "verify"),
    ("verify trusts a result whose setup failed", "scripts/delivery/gate_verify.py",
     's.get("outcome") != "pass" for s in steps', "False for s in steps", "verify"),
    ("a step may be named setup", "scripts/delivery/delivery_common.py",
     "if name == SETUP_STEP:", "if False:", "config_errors"),
    ("timeout_minutes is not validated", "scripts/delivery/delivery_common.py",
     "if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:", "if False:", "config_errors"),
    ("a partial result is published", "scripts/delivery/branch_gate.py",
     "    if (not partial or args.e2e_only) and not args.no_publish:", "    if not args.no_publish:", "only_skip"),
    ("the result is not force-pushed", "scripts/delivery/branch_gate.py",
     '"--force", remote', "remote", "publish"),
    ("fast_guards runs every step", "scripts/delivery/fast_guards.py",
     'if s["pre_push"]]', "if True]", "fast_guards"),
    ("fast_guards stops at the first failure", "scripts/delivery/fast_guards.py",
     "keep_going=True,", "keep_going=False,", "fast_report"),
    ("fast_guards has no time limit", "scripts/delivery/fast_guards.py",
     "limit_seconds=args.timeout_minutes * 60,", "limit_seconds=None,", "fast_report"),
    ("fast_guards limit is not per step", "scripts/delivery/fast_guards.py",
     "per_step=True,", "per_step=False,", "fast_report"),
    ("fast_guards default limit is 50 minutes", "scripts/delivery/delivery_common.py",
     "FAST_STEP_TIMEOUT_MINUTES = 5 ", "FAST_STEP_TIMEOUT_MINUTES = 50 ", "fast_report"),
    ("fast_guards prints no failure report", "scripts/delivery/fast_guards.py",
     "    dc.print_failures(entries, root)\n", "", "fast_report"),
    ("fast_guards logs into the gate's log directory", "scripts/delivery/fast_guards.py",
     "log_dir=dc.FAST_LOG_DIR,", "log_dir=dc.LOG_DIR,", "fast_report"),
    ("two runs share one log file", "scripts/delivery/delivery_common.py",
     'with open(part, "wb") as log:', 'with open(log_path, "wb") as log:', "fast_report"),
    ("a step inherits the caller's stdin", "scripts/delivery/delivery_common.py",
     "stdin=subprocess.DEVNULL,", "stdin=None,", "logs"),
    ("join merges an untrusted branch", "scripts/delivery/join.py",
     'if verdict is not None and not verdict["trusted"]:', "if False:", "join_untrusted"),
    ("join never resolves lockfile conflicts", "scripts/delivery/join.py",
     "if len(lock) == len(conflicts):", "if False:", "join_conflicts"),
    ("join merges fast-forward", "scripts/delivery/join.py",
     '["merge", "--no-ff", "-m"', '["merge", "--ff", "-m"', "join_clean"),
    ("join never gates the joined head", "scripts/delivery/join.py",
     "elif not args.no_gate:", "elif False:", "join_clean"),
    ("join skips the gate whatever the tree", "scripts/delivery/join.py",
     "    elif same is not None:", "    elif True:", "join_same_tree"),
    ("join skips the gate without checking the branch's result", "scripts/delivery/join.py",
     '        if gate_verify.verify(branch, base_ref, remote, root=root)["trusted"]:',
     "        if True:", "join_same_tree"),
    ("join skips the gate whatever tree the branch has", "scripts/delivery/join.py",
     "(\"refs/remotes/%s/%s\" % (remote, branch)) != tree:", "(\"refs/remotes/%s/%s\" % (remote, branch)) == \"\":", "join_same_tree"),
    ("pre-push runs for deletions", ".githooks/pre-push",
     '[ "$local_sha" = "$zero" ] && continue', "false", "hook"),
    ("pre-push does not hand the pushed commit to the guards", ".githooks/pre-push",
     'fast_guards.py --commit "$local_sha" $base_args', "fast_guards.py $base_args", "hook"),
    ("fast_guards judges the checked-out commit, not the one named", "scripts/delivery/fast_guards.py",
     'if commit != dc.rev("HEAD", root):', "if False:", "push_check"),
    ("an unknown --commit is not refused", "scripts/delivery/fast_guards.py",
     "        if commit is None:", "        if False:", "push_check"),
    ("the worktree stays after a failed or timed-out run", "scripts/delivery/fast_guards.py",
     "        return run_guards(root, path, args)\n    finally:\n        remove_worktree(root, path, links)\n",
     "        code = run_guards(root, path, args)\n        if code == 0:\n            remove_worktree(root, path, links)\n"
     "        return code\n    finally:\n        pass\n", "push_check"),
    ("the worktree stays after an interrupt", "scripts/delivery/fast_guards.py",
     "    finally:\n        remove_worktree(root, path, links)\n",
     "    finally:\n        if sys.exc_info()[0] is None:\n            remove_worktree(root, path, links)\n", "push_check"),
    ("a terminated run leaves its worktree", "scripts/delivery/fast_guards.py",
     'for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):', "for name in ():", "push_check"),
    ("node_modules is not linked", "scripts/delivery/fast_guards.py",
     "for rel in find_dependency_dirs(root):", "for rel in []:", "push_check"),
    ("node_modules is copied, not linked", "scripts/delivery/fast_guards.py",
     "if make_link(dest, root / rel):", "if shutil.copytree(root / rel, dest):", "push_check"),
    ("a link is removed by deleting what it points to", "scripts/delivery/fast_guards.py",
     "    try:\n        if os.path.islink(link):",
     "    shutil.rmtree(os.path.realpath(link), ignore_errors=True)\n    try:\n        if os.path.islink(link):", "push_check"),
    ("a link to a directory the commit lacks is made anyway", "scripts/delivery/fast_guards.py",
     "if dest.parent.is_dir() and not os.path.lexists(dest):", "if True:", "push_check"),
    ("CARGO_TARGET_DIR is not shared", "scripts/delivery/fast_guards.py",
     'os.environ["CARGO_TARGET_DIR"] = str(root / "target")', "pass", "push_check"),
    ("CARGO_TARGET_DIR of the caller is overwritten", "scripts/delivery/fast_guards.py",
     'if (root / "target").is_dir() and "CARGO_TARGET_DIR" not in os.environ:', 'if (root / "target").is_dir():', "push_check"),
    ("the steps run in the main checkout", "scripts/delivery/delivery_common.py",
     "                    cmd, cwd, env, log,", "                    cmd, root, env, log,", "push_check"),
    ("the logs are kept in the worktree", "scripts/delivery/fast_guards.py",
     "        log_root=root,\n", "        log_root=None,\n", "push_check"),
    ("pre-push never blocks", ".githooks/pre-push",
     'if [ "$fail" -ne 0 ]; then', "if false; then", "hook"),
    ("pre-push runs for result refs", ".githooks/pre-push",
     "refs/heads/*) ;;", "*) ;;", "hook"),
    ("pre-push never runs pre-push.local", ".githooks/pre-push",
     'run_local "$@"\nexit 0', "exit 0", "hook_local"),
    ("pre-push ignores a failing pre-push.local", ".githooks/pre-push",
     '    exit 1\n  }\n}', '    exit 0\n  }\n}', "hook_local"),
    ("pre-push.local gets no stdin", ".githooks/pre-push",
     '"$hooks_dir/pre-push.local" "$@" < "$stdin_file"\n  else',
     '"$hooks_dir/pre-push.local" "$@" < /dev/null\n  else', "hook_local"),
    ("an unmapped UI file does not force the whole suite", "scripts/delivery/delivery_common.py",
     'if not hits and any(f.startswith(p) for p in ctx.cfg["ui_paths"]):', "if False:", "e2e_map"),
    ("a full_on file does not force the whole suite", "scripts/delivery/delivery_common.py",
     '    if any(widen_match(f, e) for f in ctx.files for e in emap["full_on"]):',
     '    if any(widen_match(f, e) for f in ctx.files for e in []):', "e2e_map"),
    ("a widened gate still selects specs", "scripts/delivery/delivery_common.py",
     "if not emap or ctx.widened:", "if not emap:", "e2e_map"),
    ("the selection is not recorded", "scripts/delivery/delivery_common.py",
     "entry.update(e2e_info(step, ctx))", "entry.update({})", "e2e_map"),
    ("{e2e_specs} is never filled", "scripts/delivery/delivery_common.py",
     'cmd.replace("{e2e_specs}", e2e_specs)', 'cmd.replace("{e2e_specs}", "")', "e2e_map"),
    ("the full-suite command is not used for a full selection", "scripts/delivery/delivery_common.py",
     'cmd, why = step.get("run_full") or step["run"], "full suite (e2e_map)"', 'cmd, why = step["run"], "full suite (e2e_map)"',
     "e2e_map"),
    ("e2e_map is not validated", "scripts/delivery/delivery_common.py",
     'cfg["e2e_map"] = _check_e2e_map(cfg["e2e_map"], where)', "pass", "e2e_map"),
    ("the gate does not fetch its base", "scripts/delivery/delivery_common.py",
     "fetched, why_not = fetch_base(root, base_ref)", "fetched, why_not = False, None", "base_fetch"),
    ("a failed fetch is not warned about", "scripts/delivery/delivery_common.py",
     "    if why_not:\n", "    if False:\n", "base_fetch"),
    ("base_fetched is always true", "scripts/delivery/delivery_common.py",
     "base_fetched=fetched,", "base_fetched=True,", "base_fetch"),
    ("base_fetched is not in the result", "scripts/delivery/branch_gate.py",
     '        "base_fetched": ctx.base_fetched,\n', "", "scopes"),
    ("a failed fetch stops the gate", "scripts/delivery/delivery_common.py",
     "    if p.returncode == 0:\n        return True, None\n",
     "    if p.returncode == 0:\n        return True, None\n    raise DeliveryError('fetch failed')\n", "base_fetch"),
    ("a local base branch is fetched as if it were a remote", "scripts/delivery/delivery_common.py",
     "    if parts is None:\n        return False, None\n", "    if parts is None:\n        parts = ('origin', base_ref)\n", "base_fetch"),
    ("--base-ref auto is not resolved", "scripts/delivery/fast_guards.py",
     'if args.base_ref == "auto":', "if False:", "fork_point"),
    ("the farthest branch is picked, not the nearest", "scripts/delivery/delivery_common.py",
     "if best is None or key < best:", "if best is None or key > best:", "fork_point"),
    ("a tie does not go to the default branch", "scripts/delivery/delivery_common.py",
     "0 if name == default_branch else 1", "1", "fork_point"),
    ("the pushed branch can be its own base", "scripts/delivery/delivery_common.py",
     'if not name or name == "HEAD" or name == pushed_branch:', 'if not name or name == "HEAD":', "fork_point"),
    ("origin/HEAD can be the base", "scripts/delivery/delivery_common.py",
     'if not name or name == "HEAD" or name == pushed_branch:', "if not name or name == pushed_branch:", "fork_point"),
    ("--branch is ignored", "scripts/delivery/fast_guards.py",
     "args.branch or dc.current_branch(root)", "dc.current_branch(root)", "fork_point"),
    ("an unrelated branch stops --base-ref auto", "scripts/delivery/delivery_common.py",
     "        if mb.returncode != 0 or not mb.stdout.strip():\n            continue\n        n = ",
     "        n = ", "fork_point"),
    ("pre-push never asks for the fork point", ".githooks/pre-push",
     'elif [ "$remote_sha" = "$zero" ]; then', "elif false; then", "hook_auto"),
    ("pre-push ignores the sha the remote had", ".githooks/pre-push",
     'if [ "$remote_sha" != "$zero" ] && git cat-file', 'if false && git cat-file', "hook_auto"),
    ("agent_setup prints the Windows path in the PATH hint", "scripts/delivery/agent_setup.sh",
     'export PATH=\\"$bin_path:\\$PATH\\""', 'export PATH=\\"$bin_dir:\\$PATH\\""', "agent_setup"),
    ("agent_setup skips the checksum", "scripts/delivery/agent_setup.sh",
     "if got != want:", "if False:", "agent_setup"),
    ('verify accepts any base move', 'scripts/delivery/gate_verify.py',
     'if inert_ok:', 'if True:', 'inert_base'),
    ('--strict-base is ignored', 'scripts/delivery/gate_verify.py',
     'if not strict_base:', 'if True:', 'inert_base'),
    ('the inert count is not reported', 'scripts/delivery/gate_verify.py',
     'verdict["inert_commits"] = n_inert', 'verdict["inert_commits"] = 0', 'inert_base'),
    ('an inert move needs no ancestor', 'scripts/delivery/delivery_common.py',
     'if not inert_paths or not is_ancestor(old, new, cwd):', 'if not inert_paths:', 'inert_base'),
    ('every path counts as inert', 'scripts/delivery/delivery_common.py',
     'bad = [f for f in files if not any(widen_match(f, e) for e in inert_paths)]', 'bad = []', 'inert_base'),
    ('docs is not inert by default', 'scripts/delivery/delivery_common.py',
     'DEFAULT_INERT_PATHS = ["docs/**"]', 'DEFAULT_INERT_PATHS = []', 'inert_base'),
    ('an unknown lockfile_scope is accepted', 'scripts/delivery/delivery_common.py',
     'if scope not in LOCKFILE_SCOPES:', 'if False:', 'inert_base'),
    ('a root importer change does not widen', 'scripts/delivery/delivery_common.py',
     'if "." in changed:', 'if False:', 'lockfile_scope'),
    ('a change outside the importers does not widen', 'scripts/delivery/delivery_common.py',
     'if not changed and rest_a != rest_b:', 'if False:', 'lockfile_scope'),
    ('a changed importer is not a changed package', 'scripts/delivery/delivery_common.py',
     'changed = sorted(set(changed_package_dirs(files, packages)) | set(lock_dirs))', 'changed = changed_package_dirs(files, packages)', 'lockfile_scope'),
    ('a lockfile importer is not a ui change', 'scripts/delivery/delivery_common.py',
     'ui += [d for d in ctx.lock_dirs if is_ui_dir(d, ctx.cfg["ui_paths"])]', 'pass', 'lockfile_scope'),
    ('the dependency graph picks no specs', 'scripts/delivery/delivery_common.py',
     'elif not wide and "{e2e_specs}" in step["run"]:', 'elif False:', 'e2e_graph'),
    ("dependents' specs are not run", 'scripts/delivery/delivery_common.py',
     'for d in ctx.affected_dirs if is_ui_dir(d, ui_paths)}', 'for d in ctx.changed_dirs if is_ui_dir(d, ui_paths)}', 'e2e_graph'),
    ('an uncovered ui package is left out', 'scripts/delivery/delivery_common.py',
     'if not any(own.get(d) for d in users):', 'if False:', 'e2e_graph'),
    ('a ui file outside any package is ignored', 'scripts/delivery/delivery_common.py',
     'if pkg is None or not is_ui_dir(pkg, ui_paths):\n                return []', 'if pkg is None:\n                continue', 'e2e_graph'),
    ("the light check runs the tests", "scripts/delivery/join.py",
     'QUICK_STEPS = ("typecheck", "lint")', 'QUICK_STEPS = ("typecheck", "lint", "unit", "test", "e2e")', "join_quick"),
    ("the light check skips the fast guards", "scripts/delivery/join.py",
     "    if ok and guards:", "    if False:", "join_quick"),
    ("the light check ignores join_guards", "scripts/delivery/join.py",
     'guards = cfg.get("join_guards", True) and', "guards =", "join_quick"),
    ("a failed quick check still passes", "scripts/delivery/join.py",
     'ok = not timed_out and not any(e["outcome"] == "fail" for e in entries)', "ok = True", "join_quick"),
    ("a failed quick check does not stop the join", "scripts/delivery/join.py",
     '        if code != 0:\n            dc.eprint("join: the light check', '        if False:\n            dc.eprint("join: the light check', "join_quick"),
    ("the quick check records no step times", "scripts/delivery/join.py",
     '"seconds": total, "steps": steps_report,', '"seconds": total, "steps": [],', "join_quick"),
    ("--no-gate still runs the quick check", "scripts/delivery/join.py",
     "    elif not args.no_gate:\n        code, qc", "    else:\n        code, qc", "join_quick"),
    ("a push to a frozen branch is allowed", "scripts/delivery/train_freeze.py",
     "    if not running:\n        return None", "    if True:\n        return None", "freeze"),
    ("a draft PR freezes its branch", "scripts/delivery/train_freeze.py",
     'isinstance(p, dict) and not p.get("isDraft")]', "isinstance(p, dict)]", "freeze"),
    ("a finished CI still freezes", "scripts/delivery/train_freeze.py",
     'isinstance(r, dict) and r.get("status") != "completed"]', "isinstance(r, dict)]", "freeze"),
    ("the freeze override is ignored", "scripts/delivery/train_freeze.py",
     'os.environ.get("DELIVERY_FREEZE_OVERRIDE") == "1"', "False", "freeze"),
    ("the override does not say the CI restarts", "scripts/delivery/train_freeze.py",
     "The running CI will restart on the new head.", "Pushing.", "freeze"),
    ("an unreachable GitHub refuses the push", "scripts/delivery/train_freeze.py",
     'decides the merge." % (args.branch, exc), file=sys.stderr)\n        return 0', 'decides the merge." % (args.branch, exc), file=sys.stderr)\n        return 1', "freeze"),
    ("an unreachable GitHub is allowed silently", "scripts/delivery/train_freeze.py",
     'print("pre-push: warning: could not check', 'print("pre-push: could not check', "freeze"),
    ("a closed PR still freezes its branch", "scripts/delivery/train_freeze.py",
     '"--head", branch, "--state", "open", ', '"--head", branch, ', "freeze"),
    ("the freeze looks at another commit's runs", "scripts/delivery/train_freeze.py",
     '["run", "list", "--commit", sha,', '["run", "list", "--commit", "0" * 40,', "freeze"),
    ("pre-push ignores the freeze", ".githooks/pre-push",
     '--branch "${remote_ref#refs/heads/}" </dev/null || exit 1', '--branch "${remote_ref#refs/heads/}" </dev/null || true', "freeze"),
    ("a hosted label needs a runner", "scripts/delivery/runner_health.py",
     '    return "self-hosted" not in low and any(x.startswith(HOSTED_PREFIXES) for x in low)', "    return False", "runner_health"),
    ("one matching label is enough", "scripts/delivery/runner_health.py",
     "return all(n.lower() in have for n in needed)", "return any(n.lower() in have for n in needed)", "runner_health"),
    ("an offline runner counts", "scripts/delivery/runner_health.py",
     'if isinstance(r, dict) and r.get("status") == "online":', "if isinstance(r, dict):", "runner_health"),
    ("the CI_RUNS_ON variable is not read", "scripts/delivery/runner_health.py",
     "        value = var_lookup(name)\n", "        value = None\n", "runner_health"),
    ("a block list of labels is not read", "scripts/delivery/runner_health.py",
     'n = re.match(r"^\\s+-\\s*(.+)$", lines[i])', "n = None", "runner_health"),
    ("unlistable runners are not reported", "scripts/delivery/runner_health.py",
     'print("%s: check skipped: %s" % (prefix, res["reason"]))', "pass", "runner_health"),
    ("a missing runner is not a warning", "scripts/delivery/runner_health.py",
     '    if result["warnings"]:\n        result["status"] = "warn"', "    pass", "runner_health"),
]

SCENARIOS = {
    "scopes": sc_scopes,
    "affected": sc_affected,
    "step_env": sc_step_env,
    "widening": sc_widening,
    "only_skip": sc_only_skip,
    "failures": sc_failures,
    "setup": sc_setup,
    "failfast": sc_failfast,
    "logs": sc_logs,
    "timeout": sc_timeout,
    "config_errors": sc_config_errors,
    "dirty": sc_dirty,
    "publish": sc_publish,
    "verify": sc_verify,
    "fast_guards": sc_fast_guards,
    "required_steps": sc_required_steps,
    "push_check": sc_push_check,
    "fast_report": sc_fast_report,
    "parallel": sc_parallel,
    "hook_ranges": sc_hook_ranges,
    "hook": sc_hook,
    "hook_local": sc_hook_local,
    "hook_auto": sc_hook_auto,
    "e2e_map": sc_e2e_map,
    "e2e_agent": sc_e2e_agent,
    "base_fetch": sc_base_fetch,
    "fork_point": sc_fork_point,
    "join_clean": sc_join_clean,
    "join_same_tree": sc_join_same_tree,
    "join_no_gate_config": sc_join_no_gate_config,
    "join_untrusted": sc_join_untrusted,
    "join_conflicts": sc_join_conflicts,
    "join_docs_strip": sc_join_docs_strip,
    "agent_setup": sc_agent_setup,
    "assets": sc_assets,
    "packages": sc_packages,
    "inert_base": sc_inert_base,
    "lockfile_scope": sc_lockfile_scope,
    "e2e_graph": sc_e2e_graph,
    "join_quick": sc_join_quick,
    "freeze": sc_freeze,
    "runner_health": sc_runner_health,
}


def mutated_shared(rel: str, old: str, new: str) -> Path | None:
    dst = Path(tempfile.mkdtemp(dir=_TMP_ROOT, prefix="mutant-"))
    shutil.copytree(SHARED, dst / "shared", ignore=shutil.ignore_patterns("CONTRACT.md"))
    target = dst / "shared" / rel
    text = target.read_bytes().decode("utf-8").replace("\r\n", "\n")
    if text.count(old) != 1:
        return None
    target.write_bytes(text.replace(old, new).encode("utf-8"))
    return dst / "shared"


def parse_shard(text: str) -> tuple[int, int]:
    try:
        i, n = (int(x) for x in text.split("/"))
    except ValueError:
        raise argparse.ArgumentTypeError("--shard wants I/N, for example 2/4") from None
    if not 1 <= i <= n:
        raise argparse.ArgumentTypeError("--shard I/N needs 1 <= I <= N")
    return i, n


def selected_mutants(k: str | None, shard_i: int = 1, shard_n: int = 1) -> list:
    """The mutants to run: the -k filter first, then every N-th one for shard I.
    A shard may be empty (more shards than mutants); that is not a failure."""
    picked = [m for m in MUTANTS if not k or k in m[4] or k in m[0]]
    return [m for idx, m in enumerate(picked) if idx % shard_n == shard_i - 1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-mutants", action="store_true", help="skip the mutation pass")
    ap.add_argument("-k", metavar="SUBSTRING", help="run only scenarios/mutants whose name contains it")
    ap.add_argument("--shard", metavar="I/N", type=parse_shard,
                    help="CI sharding: run mutant number m (from 0) only when m %% N == I-1, "
                         "and the scenarios only in shard 1")
    ap.add_argument("--no-scenarios", action="store_true",
                    help="skip the scenarios (CI runs them in their own job beside the shards)")
    ap.add_argument("--list-mutants", action="store_true",
                    help="print the mutants this run would execute (honours --shard, -k) and exit")
    args = ap.parse_args()
    shard_i, shard_n = args.shard or (1, 1)

    if args.list_mutants:
        for label, _rel, _old, _new, scenario in selected_mutants(args.k, shard_i, shard_n):
            print(label)
        return 0

    fails = total = 0
    for name, fn in SCENARIOS.items():
        if args.k and args.k not in name:
            continue
        if shard_i != 1 or args.no_scenarios:
            break  # scenarios run in shard 1 only, and not at all with --no-scenarios
        t = T(name)
        try:
            fn(t, SHARED)
        except Exception:  # noqa: BLE001 - a crash is a failed scenario, with the trace
            t.check("scenario ran to the end", False, traceback.format_exc())
        total += t.total
        fails += len(t.failures)

    if not args.no_mutants:
        print("\n--- mutation pass: break one rule in a copy; the scenario for it must fail ---")
        for label, rel, old, new, scenario in selected_mutants(args.k, shard_i, shard_n):
            shared = mutated_shared(rel, old, new)
            total += 1
            if shared is None:
                fails += 1
                print("FAIL  mutant '%s': the text to mutate is not (uniquely) in %s; update the test" % (label, rel))
                continue
            t = T(scenario, quiet=True)
            crashed = False
            try:
                SCENARIOS[scenario](t, shared)
            except MutantStop:
                pass  # the first failed check: caught
            except Exception:  # noqa: BLE001
                crashed = True
            caught = bool(t.failures) or crashed
            print("%s  mutant '%s': %s" % (
                "PASS" if caught else "FAIL", label,
                ("caught by %d check(s)%s" % (len(t.failures), " + a crash" if crashed else "")) if caught
                else "NOT CAUGHT; scenario '%s' cannot fail on this rule" % scenario))
            fails += not caught

    print("\n%d checks, %d failed" % (total, fails))
    try:
        rmtree(_TMP_ROOT)
    except OSError:
        pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
