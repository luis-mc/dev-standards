#!/usr/bin/env python3
"""Prove the Windows learnings of CIR10 (W1 to W5) in the delivery templates.

  - windows_real.py: the Windows-only table and its guard (W3). Every broken table or shard
    must be refused.
  - artifact_prune.py --hold: installers are kept after a failed publish (W5).
  - publish_token.py: 5xx is retried with 1, 2, 4 s, a 4xx is not (W5).
  - smoke_packaged.py: an installer product needs a rollback check (W4).
  - rerun_args.py: the safe re-run on Windows paths.
  - windows-msi-linux.sh: the recipe, with stub `wine` and `xvfb-run` (the sandbox has no Wine) (W1, W2).
  - package-windows.yml: structure of the hold-until-publish rules.

Run:  python3 tools/test_delivery_windows.py
"""
from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "claude/plugins/delivery/templates/shared"
D = SHARED / "scripts/delivery"
sys.path.insert(0, str(D))

import publish_token  # noqa: E402
import rerun_args  # noqa: E402
import windows_real  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="win-learn-"))
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  " + detail))
    if not ok:
        FAILED.append(name)


def py(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


# ---------------------------------------------------------------- windows_real

def sample_project(name: str, table_over: dict | None = None, shards: dict | None = None) -> Path:
    root = TMP / name
    (root / "tests").mkdir(parents=True)
    (root / "tests/acl.test.ts").write_text("run('icacls /grant')\n", encoding="utf-8")
    table = {"schema": 1, "cap": 12, "max_minutes": 5,
             "files": [{"path": "tests/acl.test.ts", "marker": "icacls", "minutes": 1}]}
    table.update(table_over or {})
    (root / "windows-real.json").write_text(json.dumps(table), encoding="utf-8")
    (root / "ci-shards.json").write_text(json.dumps(shards or {"shards": [
        {"id": "unit-linux", "os": "linux", "commands": ["@unit"]},
        {"id": "win", "os": "windows", "set": "windows-real", "commands": ["@windows-real"],
         "files": ["tests/acl.test.ts"]}]}), encoding="utf-8")
    return root


def guard(root: Path) -> int:
    return py(str(D / "windows_real.py"), "check", "--root", str(root)).returncode


def test_guard() -> None:
    check("guard passes a good table", guard(sample_project("g-ok")) == 0)
    root = sample_project("g-marker")
    (root / "tests/acl.test.ts").write_text("plain test\n", encoding="utf-8")
    check("guard fails when a file lost its Windows marker", guard(root) == 1)
    root = sample_project("g-missing")
    (root / "tests/acl.test.ts").unlink()
    check("guard fails for a listed file that is gone", guard(root) == 1)
    check("guard fails over the cap", guard(sample_project("g-cap", {"cap": 0})) == 1)
    check("guard fails over the minutes limit", guard(sample_project("g-min", {"max_minutes": 0.5})) == 1)
    dup = {"files": [{"path": "tests/acl.test.ts", "marker": "icacls"}] * 2}
    check("guard fails for a file listed twice", guard(sample_project("g-dup", dup)) == 1)
    check("guard fails for an entry with no marker",
          guard(sample_project("g-nomark", {"files": [{"path": "tests/acl.test.ts"}]})) == 1)
    other = {"shards": [{"id": "win", "os": "windows", "commands": ["@unit"]}]}
    check("guard fails for a Windows shard that is not the table's set",
          guard(sample_project("g-other", shards=other)) == 1)
    extra = {"shards": [{"id": "win", "os": "windows", "set": "windows-real",
                         "commands": ["@windows-real", "@unit"]}]}
    check("guard fails for a Windows shard that runs another command",
          guard(sample_project("g-cmd", shards=extra)) == 1)
    unl = {"shards": [{"id": "win", "os": "windows", "set": "windows-real", "commands": ["@windows-real"],
                       "files": ["tests/other.test.ts"]}]}
    check("guard fails for a Windows shard naming an unlisted file",
          guard(sample_project("g-unl", shards=unl)) == 1)
    out = py(str(D / "windows_real.py"), "files", "--root", str(sample_project("g-files"))).stdout
    check("files prints forward-slash relative paths", out.strip() == "tests/acl.test.ts")
    check("the shipped example table is valid JSON with a cap",
          json.loads((D / "windows-real.example.json").read_text())["cap"] == 12)


# ---------------------------------------------------------------- artifact prune hold

STUB_GH = r'''
import json, os, sys
argv = sys.argv[1:]
fx = json.load(open(os.environ["GH_FX"]))
path = [a for a in argv if a.startswith("repos/")][0]
if "DELETE" in argv:
    open(os.environ["GH_DEL"], "a").write(path.rsplit("/", 1)[-1] + "\n")
    sys.exit(0)
if "/actions/workflows/" in path:
    if fx.get("runs_error"):
        sys.stderr.write("HTTP 500\n"); sys.exit(1)
    print(json.dumps({"workflow_runs": fx["runs"]})); sys.exit(0)
print(json.dumps({"artifacts": fx["artifacts"]}))
'''


def art(i: int, name: str, day: int) -> dict:
    return {"id": i, "name": name, "created_at": "2026-11-%02dT10:00:00Z" % day, "expired": False,
            "size_in_bytes": 10}


def prune(case: str, runs: list | None, runs_error: bool = False, hold: bool = True) -> list[str]:
    d = TMP / ("prune-" + case)
    (d / "bin").mkdir(parents=True)
    (d / "bin/gh.py").write_text(STUB_GH, encoding="utf-8")
    shim = d / "bin/gh"
    shim.write_text('#!/bin/sh\nexec "%s" "$(dirname "$0")/gh.py" "$@"\n' % sys.executable, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    fx = {"artifacts": [art(1, "windows-installer", 1), art(2, "windows-installer", 2),
                        art(3, "report", 1), art(4, "report", 2)],
          "runs": runs or [], "runs_error": runs_error}
    (d / "fx.json").write_text(json.dumps(fx), encoding="utf-8")
    args = ["--repo", "acme/widgets"]
    if hold:
        args += ["--hold", "windows-installer", "--hold-workflow", "package.yml"]
    py(str(D / "artifact_prune.py"), *args,
       env={"PATH": str(d / "bin") + os.pathsep + os.environ["PATH"], "GH_FX": str(d / "fx.json"),
            "GH_DEL": str(d / "del.txt")})
    f = d / "del.txt"
    return f.read_text().split() if f.exists() else []


def test_prune() -> None:
    failed = [{"status": "completed", "conclusion": "failure"}]
    ok = [{"status": "completed", "conclusion": "success"}]
    check("prune holds installers after a failed publish; other names still pruned",
          prune("failed", failed) == ["3"], str(prune("failed2", failed)))
    check("prune holds installers while the newest run is cancelled",
          prune("cancel", [{"status": "completed", "conclusion": "cancelled"}]) == ["3"])
    check("prune holds installers while the newest run is still running",
          prune("running", [{"status": "in_progress", "conclusion": None}]) == ["3"])
    check("prune holds installers when the run state cannot be read", prune("err", None, True) == ["3"])
    check("prune holds installers when no run exists", prune("none", []) == ["3"])
    check("prune prunes installers again after a successful run", sorted(prune("succ", ok)) == ["1", "3"])
    check("prune without --hold keeps the old behaviour", sorted(prune("nohold", failed, hold=False)) == ["1", "3"])
    r = py(str(D / "artifact_prune.py"), "--repo", "a/b", "--hold", "x")
    check("--hold without --hold-workflow is a usage error", r.returncode == 2)


# ---------------------------------------------------------------- publish_token

class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def script(codes: list[int]):
    seq = list(codes)

    def opener(req, timeout=0):
        code = seq.pop(0)
        if code == 200:
            return Resp(b"TOKEN")
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
    return opener


def test_token() -> None:
    sleeps: list[float] = []
    rc, body = publish_token.fetch("https://x", {}, b"", [1, 2, 4], script([503, 503, 200]), sleeps.append)
    check("token: 503, 503, then 200 gives the token after waits 1, 2", (rc, body, sleeps) == (0, "TOKEN", [1, 2]))
    sleeps = []
    rc, _ = publish_token.fetch("https://x", {}, b"", [1, 2, 4], script([500, 502, 503, 504]), sleeps.append)
    check("token: gives up after 1, 2, 4 s waits", (rc, sleeps) == (1, [1, 2, 4]))
    sleeps = []
    rc, why = publish_token.fetch("https://x", {}, b"", [1, 2, 4], script([401]), sleeps.append)
    check("token: a 4xx is not retried", (rc, sleeps, why) == (1, [], "HTTP 401"))


# ---------------------------------------------------------------- smoke rollback

def smoke(config: dict) -> subprocess.CompletedProcess:
    d = TMP / ("smoke-%d" % len(list(TMP.glob("smoke-*"))))
    (d / "scripts/delivery").mkdir(parents=True)
    for f in ("smoke_packaged.py", "delivery_common.py"):
        shutil.copy(D / f, d / "scripts/delivery" / f)
    (d / "smoke.json").write_text(json.dumps({"smoke": config}), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    # no -I: the script imports its sibling delivery_common
    return subprocess.run([sys.executable, str(d / "scripts/delivery/smoke_packaged.py"), "--config",
                           "smoke.json"], cwd=d, capture_output=True, text=True)


def test_smoke() -> None:
    base = {"start": "%s -c \"print('app ready')\"" % sys.executable, "expect": ["app ready"], "timeout_s": 20}
    r = smoke({**base, "installer": True})
    check("smoke: installer without rollback_check is refused", r.returncode == 2, r.stderr)
    r = smoke({**base, "installer": True, "rollback_check": "exit 0"})
    check("smoke: rollback checklist item is printed and passes",
          r.returncode == 0 and "verified copy of the running version" in r.stdout, r.stdout + r.stderr)
    r = smoke({**base, "installer": True, "rollback_check": "exit 3"})
    check("smoke: a failing rollback check fails the run", r.returncode == 1, r.stdout + r.stderr)
    r = smoke(base)
    check("smoke: a non-installer product is unchanged", r.returncode == 0 and "checklist" not in r.stdout)


# ---------------------------------------------------------------- rerun_args

def test_rerun() -> None:
    p = rerun_args.rerun_paths([r"C:\work\app\tests\a.test.ts", "tests\\b.test.ts"], r"C:\work\app")
    check("rerun: Windows paths become relative forward-slash", p == ["tests/a.test.ts", "tests/b.test.ts"], str(p))
    p = rerun_args.rerun_paths(["/w/app/tests/a.test.ts"], "/w/app")
    check("rerun: POSIX paths too", p == ["tests/a.test.ts"])
    try:
        rerun_args.rerun_paths([r"D:\other\x.ts"], r"C:\work\app")
        outside = False
    except ValueError:
        outside = True
    check("rerun: a file outside the test root is refused", outside)
    cmd = rerun_args.rerun_command(["vitest", "run"], ["--reporter=junit", "--outputFile", "out dir/r.xml"],
                                   [r"C:\work\app\t\a.ts"], r"C:\work\app")
    check("rerun: option values are kept", cmd == ["vitest", "run", "--reporter=junit", "--outputFile",
                                                   "out dir/r.xml", "--", "t/a.ts"], str(cmd))
    check("rerun: nothing ran and exit != 0 is a crash", rerun_args.classify_rerun(1, 0, 0) == "crash")
    check("rerun: a test failed again is failed", rerun_args.classify_rerun(1, 3, 1) == "failed")
    check("rerun: green is passed", rerun_args.classify_rerun(0, 3, 0) == "passed")


# ---------------------------------------------------------------- Linux MSI recipe

def test_recipe() -> None:
    d = TMP / "msi"
    (d / "bin").mkdir(parents=True)
    (d / "cache/tools").mkdir(parents=True)
    tool = d / "cache/tools/build.py"
    tool.write_text("import os, sys\nout = sys.argv[1]\nos.makedirs(out, exist_ok=True)\n"
                    "open(out + '/app.msi', 'w').write('compression=' + os.environ['MSI_COMPRESSION'])\n",
                    encoding="utf-8")
    import hashlib
    sha = hashlib.sha256(tool.read_bytes()).hexdigest()
    for name, body in (("wine", 'exec python3 "$@"'), ("xvfb-run", 'shift; exec "$@"')):
        (d / "bin" / name).write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        (d / "bin" / name).chmod(0o755)
    tools = {"tools": [{"name": "t", "url": "https://example.invalid/t", "sha256": sha, "file": "build.py"}],
             "build": {"exe": "build.py", "args": ["{out}"]}}
    (d / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    env = {"PATH": str(d / "bin") + os.pathsep + os.environ["PATH"]}
    run = lambda *a: subprocess.run(["bash", str(D / "windows-msi-linux.sh"), "--tools", str(d / "tools.json"),
                                     "--cache", str(d / "cache"), "--out", str(d / "out"), *a],
                                    capture_output=True, text=True, env={**os.environ, **env}, cwd=d)
    r = run("--dry-run")
    check("recipe: dry run lists the steps and builds nothing",
          r.returncode == 0 and "would:" in r.stdout and not (d / "out").exists(), r.stdout + r.stderr)
    r = run()
    msi = d / "out/app.msi"
    check("recipe: builds an MSI in the sample project (stub wine)", r.returncode == 0 and msi.exists(), r.stderr)
    check("recipe: the compression level is mszip, not LZX/high",
          msi.exists() and msi.read_text() == "compression=mszip")
    check("recipe: says it is a check only", "check only" in r.stdout)
    tools["tools"][0]["sha256"] = "0" * 64
    (d / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    check("recipe: a tool with the wrong SHA-256 fails", run().returncode == 1)
    text = (D / "windows-msi-linux.sh").read_text()
    check("recipe: tools start by full path, never through PATH", '"$TOOLDIR/$EXE"' in text)


# ---------------------------------------------------------------- workflows

def test_workflows() -> None:
    pw = (SHARED / ".github/workflows/package-windows.yml").read_text()
    check("package-windows: clean-up runs only when nothing failed or was cancelled",
          "contains(needs.*.result, 'failure')" in pw and "contains(needs.*.result, 'cancelled')" in pw
          and "needs: [build, publish]" in pw)
    check("package-windows: the token comes from the retrying script", "publish_token.py" in pw)
    check("package-windows: the installer is built on Windows", "runs-on: windows-latest" in pw)
    chk = (SHARED / ".github/workflows/windows-msi-check.yml").read_text()
    check("msi check: says check only and uses the recipe", "CHECK ONLY" in chk and "windows-msi-linux.sh" in chk)
    ap = (SHARED / ".github/workflows/artifact-prune.yml").read_text()
    check("artifact-prune: documents the hold", "--hold windows-installer --hold-workflow" in ap)


def main() -> int:
    for t in (test_guard, test_prune, test_token, test_smoke, test_rerun, test_recipe, test_workflows):
        t()
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n%s" % ("all passed" if not FAILED else "FAILED: " + ", ".join(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
