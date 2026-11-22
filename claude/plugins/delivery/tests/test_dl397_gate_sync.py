"""DL397: update merges gate.json by step name; the doctor flags a missing e2e step; template test steps carry a timeout.
DL400: the pre-push hook ignores deleted files."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import _helpers  # noqa: F401
import delivery_ci_install as INS
import delivery_doctor as DOC

PLUGIN = Path(__file__).resolve().parents[1]
HOOK = PLUGIN / "templates" / "shared" / ".githooks" / "pre-push"
GATE = "scripts/delivery/gate.json"


def run(*argv):
    out = StringIO()
    with redirect_stdout(out), redirect_stderr(StringIO()):
        code = INS.main(list(argv))
    return code, out.getvalue()


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=t", *a],
                          cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


class Sync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        run("install", "--track", "ts", "--root", str(self.root))
        self.path = self.root / GATE

    def test_keeps_project_step_and_adds_missing(self):
        gate = json.loads(self.path.read_text())
        mine = {"name": "unit", "scope": "changed", "run": "my own unit run"}
        gate["steps"] = [s for s in gate["steps"] if s["name"] not in ("unit", "e2e")] + [mine]
        self.path.write_text(json.dumps(gate, indent=2))
        code, out = run("update", "--track", "ts", "--root", str(self.root))
        self.assertEqual(code, 0)
        steps = {s["name"]: s for s in json.loads(self.path.read_text())["steps"]}
        self.assertEqual(steps["unit"], mine)
        self.assertEqual(steps["e2e"]["scope"], "ui-changed")
        self.assertIn("added step(s)", out)
        self.assertIn("e2e", out)

    def test_nothing_missing_leaves_file_alone(self):
        gate = json.loads(self.path.read_text())
        gate["steps"][0]["run"] = "changed by the project"
        text = json.dumps(gate, indent=1)
        self.path.write_text(text)
        run("update", "--track", "ts", "--root", str(self.root))
        self.assertEqual(self.path.read_text(), text)


class Doctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "scripts" / "delivery").mkdir(parents=True)
        (self.root / "e2e").mkdir()
        (self.root / "e2e" / "a.spec.ts").write_text("x\n")
        self.gate({"steps": [{"name": "unit", "scope": "changed", "run": "x"}]})

    def gate(self, data):
        (self.root / GATE).write_text(json.dumps(data))
        git(self.root, "add", ".")

    def test_flags_missing_e2e_step(self):
        res = DOC.check_gate_steps(str(self.root), {})
        self.assertFalse(res[0])
        self.assertIn("no e2e step in gate.json", res[1])

    def test_quiet_with_step_or_without_specs(self):
        self.gate({"steps": [{"name": "e2e", "scope": "ui-changed", "run": "x"}]})
        self.assertIsNone(DOC.check_gate_steps(str(self.root), {}))
        self.gate({"steps": [{"name": "unit", "scope": "changed", "run": "x"}], "e2e_spec_paths": ["none/*.x"]})
        self.assertIsNone(DOC.check_gate_steps(str(self.root), {}))


class PushCheck(unittest.TestCase):
    def test_no_e2e_step_gives_a_hint_not_a_block(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        git(d, "init", "-q", "-b", "main")
        sd = d / "scripts" / "delivery"
        sd.mkdir(parents=True)
        for f in (PLUGIN / "templates" / "shared" / "scripts" / "delivery").glob("*.py"):
            shutil.copy(f, sd / f.name)
        shutil.copy(PLUGIN / "templates" / "go" / "scripts" / "delivery" / "gate.json", sd / "gate.json")
        (d / "a.txt").write_text("x\n")
        git(d, "add", ".")
        git(d, "commit", "-qm", "base")
        base = git(d, "rev-parse", "HEAD")
        (d / "e2e").mkdir()
        (d / "e2e" / "a.spec.ts").write_text("x\n")
        git(d, "add", ".")
        git(d, "commit", "-qm", "spec")
        r = subprocess.run(["python3", "scripts/delivery/e2e_push_check.py", "--commit", "HEAD", "--base-ref", base],
                           cwd=str(d), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no e2e step in gate.json", r.stderr)


class Timeouts(unittest.TestCase):
    def test_every_test_step_has_a_timeout(self):
        rx = {"go": r"-timeout", "ts": r"--testTimeout=|--timeout=", "dotnet": r"--blame-hang-timeout"}
        for track, pat in rx.items():
            gate = json.loads((PLUGIN / "templates" / track / "scripts" / "delivery" / "gate.json").read_text())
            for step in gate["steps"]:
                for key in ("run", "run_full"):
                    cmd = step.get(key, "")
                    if re.search(r"go test|vitest run|dotnet test", cmd):
                        self.assertRegex(cmd, pat, "%s %s %s" % (track, step["name"], key))


class PrePushDeletedPackage(unittest.TestCase):
    def test_deleting_a_go_package_pushes(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        git(d, "init", "-q", "-b", "main")
        sd = d / "scripts" / "delivery"
        sd.mkdir(parents=True)
        (sd / "fast_guards.py").write_text("import sys\nsys.exit(0)\n")
        (sd / "gate.json").write_text('{"steps":[{"command":"pnpm exec tsc"}]}\n')
        (d / "package.json").write_text("{}\n")
        (d / "pnpm-lock.yaml").write_text("x\n")
        (d / "pkg").mkdir()
        (d / "pkg" / "a.js").write_text("x\n")   # the deleted package's file; a deleted file is not a JS input
        git(d, "add", ".")
        git(d, "commit", "-qm", "base")
        base = git(d, "rev-parse", "HEAD")
        git(d, "rm", "-rq", "pkg")
        git(d, "commit", "-qm", "delete pkg")
        head = git(d, "rev-parse", "HEAD")
        line = "refs/heads/t %s refs/heads/t %s\n" % (head, base)
        r = subprocess.run(["sh", str(HOOK), "origin", "url"], cwd=str(d), input=line, capture_output=True, text=True,
                           env=dict(os.environ, PRE_PUSH_REEXEC="1"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("node checks skipped", r.stderr)


if __name__ == "__main__":
    unittest.main()
