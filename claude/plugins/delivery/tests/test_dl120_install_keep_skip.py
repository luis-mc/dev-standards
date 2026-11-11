"""DL120: ci-install.json keep and skip lists for install and update."""
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401  (puts the plugin scripts on sys.path)
import delivery_ci_install as INS

WATCH = "scripts/delivery/ci_watch.py"
WF = ".github/workflows/package-windows.yml"
CFG = "scripts/delivery/ci-install.json"


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


class KeepSkip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def path(self, rel):
        return os.path.join(self.tmp, rel.replace("/", os.sep))

    def write(self, rel, text):
        os.makedirs(os.path.dirname(self.path(rel)), exist_ok=True)
        with open(self.path(rel), "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as f:
            return f.read()

    def config(self, keep=(), skip=()):
        self.write(CFG, json.dumps({"keep": list(keep), "skip": list(skip)}))

    def test_kept_file_survives_update_and_is_reported(self):
        self.assertEqual(run("install", "--track", "ts", "--root", self.tmp)[0], 0)
        self.write(WATCH, "# my fix\n")
        self.config(keep=[WATCH])
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read(WATCH), "# my fix\n")
        self.assertIn("kept (ci-install.json) " + WATCH, out)
        self.assertIn("kept %s: the plugin's version differs; diff it with " % WATCH, out)
        self.assertIn("fold your change into the plugin or drop it", out)

    def test_without_keep_an_edited_file_is_kept_with_a_new_file(self):
        run("install", "--track", "ts", "--root", self.tmp)
        shutil.rmtree(os.path.join(self.tmp, ".delivery", "ci-install-base"))   # no base: kept with a .new
        self.write(WATCH, "# my fix\n")
        run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(self.read(WATCH), "# my fix\n")        # DL201: kept, not overwritten
        self.assertNotEqual(self.read(WATCH + ".new"), "# my fix\n")

    def test_skipped_workflow_not_written(self):
        sources = {rel for rel, _s, _a in INS.plan("ts", self.tmp, "install")}
        wf = next(r for r in sorted(sources) if r.startswith(".github/workflows/"))
        self.config(skip=[wf])
        for action in ("install", "update"):
            code, out = run(action, "--track", "ts", "--root", self.tmp)
            self.assertEqual(code, 0, out)
            self.assertFalse(os.path.exists(self.path(wf)))
            self.assertIn("skipped (ci-install.json) " + wf, out)

    def test_config_never_overwritten(self):
        text = json.dumps({"keep": [], "skip": []})
        self.write(CFG, text)
        run("install", "--track", "ts", "--root", self.tmp)
        run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(self.read(CFG), text)
        self.assertTrue(os.path.exists(self.path("scripts/delivery/ci-install.example.json")))

    def test_unknown_path_warns(self):
        self.config(keep=["scripts/delivery/nope.py"], skip=["other/file.yml"])
        code, out = run("install", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("warning:", out)
        self.assertIn("scripts/delivery/nope.py", out)
        self.assertIn("other/file.yml", out)

    def test_bad_json_exits_2(self):
        self.write(CFG, "{not json")
        code, out = run("update", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 2)
        self.assertIn("ci-install.json", out)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertFalse(os.path.exists(self.path(WATCH)))

    def test_no_config_behaves_as_before(self):
        code, out = run("install", "--track", "ts", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertNotIn("ci-install.json", out)
        self.assertFalse(os.path.exists(self.path(CFG)))


if __name__ == "__main__":
    unittest.main()
