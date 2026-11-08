"""DL112: the installer reports missing sibling imports and untracked files; ci_watch names a missing module."""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import _helpers  # noqa: F401  (puts the plugin scripts on sys.path)
import delivery_ci_install as INS

TEMPLATES = Path(INS.TEMPLATES)
SCRIPTS = "scripts/delivery"


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue()


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class ShippedClosure(unittest.TestCase):
    def test_every_local_import_ships(self):
        for track in INS.TRACKS:
            shipped = set()
            for part in ("shared", track):
                shipped.update(INS.files_of(str(TEMPLATES / part)))
            for rel in sorted(shipped):
                if not (rel.startswith(SCRIPTS + "/") and rel.endswith(".py")):
                    continue
                src = TEMPLATES / ("shared" if (TEMPLATES / "shared" / rel).exists() else track) / rel
                for name in INS.imported_names(str(src)):
                    local = (TEMPLATES / "shared" / SCRIPTS / (name + ".py"), TEMPLATES / track / SCRIPTS / (name + ".py"))
                    stdlib = name in sys.stdlib_module_names
                    plugin_only = (Path(INS.PLUGIN) / "scripts" / (name + ".py")).exists()  # optional, found at run time
                    if not stdlib and not plugin_only and not any(p.exists() for p in local):
                        self.fail("%s (%s) imports %s, which is not shipped" % (rel, track, name))


class InstallChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        git(self.tmp, "init", "-q")

    def test_missing_import_reported_and_exit_3(self):
        code, _ = run("install", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0)
        os.remove(os.path.join(self.tmp, SCRIPTS, "ci_fallback.py"))
        code, out = run("update", "--track", "ts", "--root", self.tmp, "--dry-run")
        self.assertEqual(code, 3)
        self.assertIn("missing imports:", out)
        self.assertIn("fallback_launch.py imports ci_fallback.py", out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, SCRIPTS, "ci_fallback.py")))
        code, out = run("update", "--track", "ts", "--root", self.tmp)  # real update restores it
        self.assertEqual(code, 0)
        self.assertNotIn("missing imports:", out)

    def test_untracked_listed_then_tracked(self):
        code, out = run("install", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0)
        self.assertIn("not in git yet (commit them):", out)
        self.assertIn(SCRIPTS + "/ci_fallback.py", out)
        git(self.tmp, "add", "-A")
        _, out = run("update", "--track", "ts", "--root", self.tmp, "--dry-run")
        self.assertNotIn("not in git yet", out)

    def test_no_git_no_heading(self):
        plain = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, plain, True)
        _, out = run("install", "--track", "ts", "--root", plain)
        self.assertNotIn("not in git yet", out)


class WatcherError(unittest.TestCase):
    def test_ci_watch_names_missing_file(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        src = TEMPLATES / "shared" / SCRIPTS
        for name in ("ci_watch.py", "runner_health.py", "fallback_launch.py"):
            shutil.copyfile(src / name, os.path.join(tmp, name))
        proc = subprocess.run([sys.executable, "-I", os.path.join(tmp, "ci_watch.py"), "--help"],
                              capture_output=True, text=True, cwd=tmp)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ci_fallback.py", proc.stderr)
        self.assertIn("delivery_ci_install.py update --track", proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
