"""DL392: the pre-push hook skips the node checks for a push with no JS file when node_modules is missing."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "templates" / "shared" / ".githooks" / "pre-push"


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=t", *a],
                          cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


class NoNode(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        git(self.d, "init", "-q", "-b", "main")
        sd = self.d / "scripts" / "delivery"
        sd.mkdir(parents=True)
        (sd / "gate.json").write_text('{"steps":[{"command":"pnpm exec tsc"}]}\n')
        (sd / "fast_guards.py").write_text("import sys\nsys.exit(0)\n")
        (self.d / "package.json").write_text("{}\n")
        (self.d / "pnpm-lock.yaml").write_text("x\n")
        git(self.d, "add", ".")
        git(self.d, "commit", "-qm", "base")
        self.base = git(self.d, "rev-parse", "HEAD")

    def push(self, name):
        (self.d / name).write_text("x\n")
        git(self.d, "add", ".")
        git(self.d, "commit", "-qm", name)
        head = git(self.d, "rev-parse", "HEAD")
        line = "refs/heads/t %s refs/heads/t %s\n" % (head, self.base)
        return subprocess.run(["sh", str(HOOK), "origin", "url"], cwd=str(self.d), input=line,
                              capture_output=True, text=True, env=dict(__import__("os").environ, PRE_PUSH_REEXEC="1"))

    def test_docs_only_push_skips_node_checks(self):
        r = self.push("notes.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("node checks skipped", r.stderr)

    def test_js_push_still_blocks(self):
        r = self.push("app.ts")
        self.assertEqual(r.returncode, 1)
        self.assertIn("node_modules is missing", r.stderr)


if __name__ == "__main__":
    unittest.main()
