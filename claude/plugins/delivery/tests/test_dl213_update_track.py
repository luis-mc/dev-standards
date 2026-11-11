"""DL213: update reads the track from the project; the install record keeps it."""
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401
import delivery_ci_install as INS


def run(*argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = INS.main(list(argv))
    return code, out.getvalue() + err.getvalue()


class UpdateTrack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def state(self):
        with open(os.path.join(self.tmp, INS.STATE.replace("/", os.sep)), encoding="utf-8") as f:
            return json.load(f)

    def test_update_uses_recorded_track(self):
        self.assertEqual(run("install", "--track", "rust", "--root", self.tmp)[0], 0)
        self.assertEqual(self.state()["track"], "rust")
        code, out = run("update", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn("using track rust", out)
        self.assertEqual(self.state()["track"], "rust")

    def test_update_reads_config_first(self):
        os.makedirs(os.path.join(self.tmp, ".delivery"))
        with open(os.path.join(self.tmp, ".delivery", "config.json"), "w") as f:
            json.dump({"track": "go"}, f)
        code, out = run("update", "--root", self.tmp)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.state()["track"], "go")

    def test_no_config_no_state_is_a_clear_error(self):
        code, out = run("update", "--root", self.tmp)
        self.assertEqual(code, 1)
        self.assertIn("--track must be one of ts, go, rust, dotnet", out)

    def test_explicit_track_wins(self):
        run("install", "--track", "rust", "--root", self.tmp)
        self.assertEqual(run("update", "--track", "go", "--root", self.tmp)[0], 0)
        self.assertEqual(self.state()["track"], "go")


if __name__ == "__main__":
    unittest.main()
