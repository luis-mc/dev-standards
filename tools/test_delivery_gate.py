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

Run:  python3 tools/test_delivery_gate.py [--no-mutants] [-k SUBSTRING]
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
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
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
    "join.py", "agent_setup.sh", "tools.json",
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
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GATE_TEST_FAIL", "GIT_PREFIX"):
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


class T:
    """Records the checks of one scenario."""

    def __init__(self, name: str, quiet: bool = False):
        self.name, self.quiet = name, quiet
        self.total = 0
        self.failures: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.total += 1
        if not ok:
            self.failures.append(label)
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
        "import json, os, sys\n"
        "name, args = sys.argv[1], sys.argv[2:]\n"
        "os.makedirs('.delivery', exist_ok=True)\n"
        "with open('.delivery/ran.log', 'a') as f:\n"
        "    f.write(json.dumps([name] + args) + '\\n')\n"
        "sys.exit(1 if name in os.environ.get('GATE_TEST_FAIL', '').split(',') else 0)\n"
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
        (d / "_t.py").write_text(self.STEP_SCRIPT, encoding="utf-8", newline="\n")
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

    def ran(self) -> list:
        log = self.work / ".delivery/ran.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines() if line]

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
         sorted(res), sorted(["schema", "kind", "branch", "head", "base", "base_ref", "widened",
                              "changed_dirs", "steps", "pass", "partial", "started_at",
                              "finished_at", "tool"]))
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
    t.eq("result: step shape", sorted(res["steps"][0])[:4], ["command", "name", "outcome", "reason"])
    t.check("result: command recorded with placeholders filled",
            "apps/web" in res["steps"][0]["command"] and "{" not in res["steps"][0]["command"])
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
    r = box.gate("--no-publish", env={"GATE_TEST_FAIL": "lint"})
    t.eq("a failing step: exit 1", r.code, 1)
    t.eq("a failing step: later steps still ran",
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
    t.eq("garbage result: exit 1", verify(box, "feat/garbage").code, 1)
    t.eq("unknown schema: exit 1", verify(box, "feat/oldschema").code, 1)

    # default --base-ref and --remote
    r = box.script("gate_verify.py", "feat/ok", "--remote", "origin")
    t.eq("default base ref is <remote>/<default_branch>", r.code, 0)

    # now main moves on: every earlier result has a stale base
    box.g("checkout", "-q", "main")
    box.commit({"docs/main2.txt": "m\n"}, "main moves")
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
    res = box.result()
    t.eq("the gate ran on the joined head", res["head"], box.g("rev-parse", "HEAD"))
    t.eq("... against the default branch", res["base_ref"], "origin/main")
    t.eq("... covering both branches' packages", res["changed_dirs"], ["apps/api", "apps/web"])
    t.eq("... and passed", res["pass"], True)
    t.eq("nothing pushed without --push", box.g("rev-parse", "origin/integ"), integ_before)
    t.eq("... and no result published without --push", box.remote_ref("refs/gate-results/integ"), None)
    t.eq("working tree left clean", box.clean(), True)

    # --push, in a second box
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    r = join(box, "--into", "integ", "feat/a", "--push")
    t.eq("--push: exit 0", r.code, 0)
    head = box.g("rev-parse", "HEAD")
    t.eq("--push: integration pushed", box.g("rev-parse", "origin/integ"), head)
    ref = box.remote_ref("refs/gate-results/integ")
    t.check("--push: its gate result published", ref is not None)
    t.eq("--push: the result is for the pushed head and passes",
         json.loads(box.origin_git("show", "refs/gate-results/integ:gate-result.json"))["head"], head)
    t.eq("--push: gate_verify trusts the pushed integration branch",
         verify(box, "integ", base_ref="origin/main").code, 0)

    # --no-gate
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    box.clear_log()
    r = join(box, "--into", "integ", "feat/a", "--no-gate")
    t.eq("--no-gate: exit 0, nothing ran", (r.code, box.ran()), (0, []))

    # a failing gate on the joined head blocks the push
    box = integ_box(shared)
    box.gated("feat/a", {"apps/web/a.txt": "a\n"}, frm="integ", base_ref="origin/integ")
    before = box.g("rev-parse", "origin/integ")
    r = join(box, "--into", "integ", "feat/a", "--push", env={"GATE_TEST_FAIL": "unit"})
    t.eq("a failing gate on the joined head: exit 1", r.code, 1)
    t.eq("... and nothing is pushed", box.g("rev-parse", "origin/integ"), before)

    # preconditions
    r = join(box, "--into", "no-such-integration", "feat/a")
    t.eq("unknown integration branch: exit 2", r.code, 2)
    box.write("docs/dirty.txt", "d\n")
    r = join(box, "--into", "integ", "feat/a")
    t.eq("dirty working tree: exit 2", r.code, 2)


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
    t.eq("... setup was re-run", [x[0] for x in box.ran()], ["setup"])
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

    version = json.loads((shared / "scripts/delivery/tools.json").read_text())["gitleaks"]
    box = Box(shared)
    sh = box.work / "scripts/delivery/agent_setup.sh"
    path = Path(PY).parent.as_posix() + os.pathsep + os.environ.get("PATH", "")
    base_env = {"PATH": path}

    dry = run([bash, sh.as_posix()], cwd=box.work, extra_env={**base_env, "DELIVERY_DRY_RUN": "1"})
    t.eq("dry run: exit 0", dry.code, 0)
    url = dry.out.strip().splitlines()[-1] if dry.out.strip() else ""
    asset = url.rsplit("/", 1)[-1]
    want = expected_asset(version)
    t.check("dry run: the URL points at the pinned release on GitHub",
            url.startswith("https://github.com/gitleaks/gitleaks/releases/download/v%s/" % version), url)
    if want:
        t.eq("dry run: asset name for this OS and CPU", asset, want)

    # serve a fake release
    srv_dir = box.root / "release"
    srv_dir.mkdir()
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
    (srv_dir / asset).write_bytes(archive)
    sums = "%s  %s\n%s  other_%s\n" % (hashlib.sha256(archive).hexdigest(), asset, "0" * 64, asset)
    (srv_dir / ("gitleaks_%s_checksums.txt" % version)).write_text(sums)

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
        t.eq("... gate.json setup ran", [x[0] for x in box.ran()], ["setup"])
        t.eq("... hooks path set", box.g("config", "--get", "core.hooksPath"), ".githooks")
        if exe == "gitleaks":
            box.clear_log()
            r = run([bash, sh.as_posix()], cwd=box.work, extra_env=env)
            t.eq("idempotent: second run exit 0", r.code, 0)
            t.has("idempotent: skips the download", r.err, "already installed")
            t.eq("idempotent: setup runs again", [x[0] for x in box.ran()], ["setup"])

        # a tampered archive must not be installed
        (srv_dir / ("gitleaks_%s_checksums.txt" % version)).write_text("%s  %s\n" % ("1" * 64, asset))
        bad_bin = box.root / "bad-bin"
        r = run([bash, sh.as_posix()], cwd=box.work,
                extra_env={**env, "DELIVERY_BIN": bad_bin.as_posix()})
        t.eq("checksum mismatch: exit 2", r.code, 2)
        t.has("... says mismatch", r.err, "checksum mismatch")
        t.eq("... nothing installed", (bad_bin / exe).exists(), False)
        (srv_dir / ("gitleaks_%s_checksums.txt" % version)).write_text("%s  other\n" % ("1" * 64))
        r = run([bash, sh.as_posix()], cwd=box.work,
                extra_env={**env, "DELIVERY_BIN": bad_bin.as_posix()})
        t.eq("asset missing from the checksums file: exit 2", r.code, 2)
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

def sc_assets(t: T, shared: Path) -> None:
    tools = json.loads((shared / "scripts/delivery/tools.json").read_text())
    ver = tools.get("gitleaks", "")
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
        steps = {s["name"]: s for s in cfg["steps"]}
        t.check(label + ": guards and secret-scan are pre_push and always",
                all(steps.get(n, {}).get("pre_push") and steps[n]["scope"] == "always"
                    for n in ("guards", "secret-scan")))
        t.check(label + ": secret-scan uses `gitleaks git` over {base}..HEAD",
                "gitleaks git " in steps["secret-scan"]["run"] and "--log-opts={base}..HEAD" in steps["secret-scan"]["run"])
        t.check(label + ": only known placeholders",
                all(set(re.findall(r"\{(\w+)\}", s.get("run", "") + s.get("run_full", ""))) <= {"base", "changed_dirs"}
                    for s in cfg["steps"]))
        t.check(label + ": has typecheck, lint-or-build and unit steps",
                {"typecheck", "unit"} <= set(steps))
        t.check(label + ": no single quotes in commands (cmd.exe)",
                all("'" not in s.get("run", "") + s.get("run_full", "") for s in cfg["steps"]))
    ts = json.loads((TOOLING / "ts/scripts/delivery/gate.json").read_text())
    t.check("ts gate.json matches the contract example commands",
            any("--filter" in s["run"] and "{base}" in s["run"] for s in ts["steps"] if s["name"] == "typecheck")
            and any(s["name"] == "unit" and "{changed_dirs}" in s["run"] and "--project unit" in s["run"] for s in ts["steps"]))
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
    hook = (shared / ".githooks/pre-push").read_text(encoding="utf-8")
    t.check("pre-push is a POSIX sh script", hook.startswith("#!/bin/sh"))


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
# mutation pass
# --------------------------------------------------------------------------

# (id, file relative to shared/, text to replace, replacement, scenario that must notice)
MUTANTS = [
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
    ("gate never widens", "scripts/delivery/delivery_common.py",
     'reasons = widening_files(files, cfg["widen_on"])', "reasons = []", "widening"),
    ("--fail-fast does not stop", "scripts/delivery/delivery_common.py",
     "stopped = fail_fast", "stopped = False", "failures"),
    ("a failing gate still exits 0", "scripts/delivery/branch_gate.py",
     "exit_code = dc.EXIT_OK if ok else dc.EXIT_FAIL", "exit_code = dc.EXIT_OK", "failures"),
    ("a partial result is published", "scripts/delivery/branch_gate.py",
     "    if partial:\n        print(\"note", "    if False:\n        print(\"note", "only_skip"),
    ("the result is not force-pushed", "scripts/delivery/branch_gate.py",
     '"--force", remote', "remote", "publish"),
    ("fast_guards runs every step", "scripts/delivery/fast_guards.py",
     'if s["pre_push"]]', "if True]", "fast_guards"),
    ("join merges an untrusted branch", "scripts/delivery/join.py",
     'if not verdict["trusted"]:', "if False:", "join_untrusted"),
    ("join never resolves lockfile conflicts", "scripts/delivery/join.py",
     "if len(lock) == len(conflicts):", "if False:", "join_conflicts"),
    ("join merges fast-forward", "scripts/delivery/join.py",
     '["merge", "--no-ff", "-m"', '["merge", "--ff", "-m"', "join_clean"),
    ("join never gates the joined head", "scripts/delivery/join.py",
     "if not args.no_gate:", "if False:", "join_clean"),
    ("pre-push runs for deletions", ".githooks/pre-push",
     '[ "$local_sha" = "$zero" ] && continue', "false", "hook"),
    ("pre-push never blocks", ".githooks/pre-push",
     'if [ "$fail" -ne 0 ]; then', "if false; then", "hook"),
    ("pre-push runs for result refs", ".githooks/pre-push",
     "refs/heads/*) ;;", "*) ;;", "hook"),
    ("agent_setup skips the checksum", "scripts/delivery/agent_setup.sh",
     "if got != want:", "if False:", "agent_setup"),
]

SCENARIOS = {
    "scopes": sc_scopes,
    "widening": sc_widening,
    "only_skip": sc_only_skip,
    "failures": sc_failures,
    "config_errors": sc_config_errors,
    "dirty": sc_dirty,
    "publish": sc_publish,
    "verify": sc_verify,
    "fast_guards": sc_fast_guards,
    "hook": sc_hook,
    "join_clean": sc_join_clean,
    "join_untrusted": sc_join_untrusted,
    "join_conflicts": sc_join_conflicts,
    "agent_setup": sc_agent_setup,
    "assets": sc_assets,
    "packages": sc_packages,
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-mutants", action="store_true", help="skip the mutation pass")
    ap.add_argument("-k", metavar="SUBSTRING", help="run only scenarios/mutants whose name contains it")
    args = ap.parse_args()

    fails = total = 0
    for name, fn in SCENARIOS.items():
        if args.k and args.k not in name:
            continue
        t = T(name)
        try:
            fn(t, SHARED)
        except Exception:  # noqa: BLE001 - a crash is a failed scenario, with the trace
            t.check("scenario ran to the end", False, traceback.format_exc())
        total += t.total
        fails += len(t.failures)

    if not args.no_mutants:
        print("\n--- mutation pass: break one rule in a copy; the scenario for it must fail ---")
        for label, rel, old, new, scenario in MUTANTS:
            if args.k and args.k not in scenario and args.k not in label:
                continue
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
