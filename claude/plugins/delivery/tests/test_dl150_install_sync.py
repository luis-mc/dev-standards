"""DL150: `update` syncs artifact_prune.workflows after it rewrites artifact-prune.yml."""
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import _helpers  # noqa: F401
import delivery_ci_install as INS

WF = ".github/workflows/artifact-prune.yml"


def run(*argv):
    out = StringIO()
    with redirect_stdout(out), redirect_stderr(StringIO()):
        code = INS.main(list(argv))
    return code, out.getvalue()


class Sync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        run("install", "--track", "ts", "--root", str(self.root))

    def test_update_applies_project_list(self):
        (self.root / ".delivery").mkdir()
        (self.root / ".delivery" / "config.json").write_text('{"artifact_prune": {"workflows": ["CI", "Installers"]}}')
        (self.root / WF).write_text("old\n")
        code, out = run("update", "--track", "ts", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("Installers", (self.root / WF).read_text())
        self.assertIn("synced", out)

    def test_failed_sync_keeps_update(self):
        (self.root / ".delivery").mkdir()
        (self.root / ".delivery" / "config.json").write_text("{not json")
        (self.root / WF).write_text("old\n")
        code, out = run("update", "--track", "ts", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("could not sync", out)
        self.assertIn("--sync-workflow", out)
        self.assertNotEqual((self.root / WF).read_text(), "old\n")

    def test_no_sync_when_workflow_same(self):
        code, out = run("update", "--track", "ts", "--root", str(self.root))
        self.assertNotIn("sync", out)

    def test_dry_run_does_not_sync(self):
        (self.root / WF).write_text("old\n")
        code, out = run("update", "--track", "ts", "--root", str(self.root), "--dry-run")
        self.assertEqual((self.root / WF).read_text(), "old\n")
        self.assertNotIn("synced", out)


if __name__ == "__main__":
    unittest.main()
