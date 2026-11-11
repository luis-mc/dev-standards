"""DL236: a file the installer just wrote never makes the doctor warn ci.scripts-current; a project edit still does."""
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import _helpers  # noqa: F401
import delivery_ci_install as INS
import delivery_doctor as DOC

GATE = "scripts/delivery/branch_gate.py"
RERUN = "scripts/delivery/ci_rerun_first.py"


def install(*argv):
    out = StringIO()
    with redirect_stdout(out), redirect_stderr(StringIO()):
        INS.main(list(argv))
    return out.getvalue()


class ScriptsCurrent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def p(self, rel):
        return os.path.join(self.tmp, rel.replace("/", os.sep))

    def item(self):
        return [i for i in DOC.scripts_items(self.tmp) if i["id"] == "ci.scripts-current"][0]

    def read(self, rel):
        with open(self.p(rel), "rb") as f:
            return f.read()

    def write(self, rel, data):
        with open(self.p(rel), "wb") as f:
            f.write(data)

    def older(self, crlf=False):
        for rel in (GATE, RERUN):
            data = b"# older copy\n" + self.read(rel).replace(b"\r\n", b"\n")
            self.write(rel, data.replace(b"\n", b"\r\n") if crlf else data)

    def record(self):
        sp = self.p(INS.STATE)
        with open(sp, encoding="utf-8") as f:
            data = json.load(f)
        for rel in (GATE, RERUN):
            data["files"][rel] = INS.digest(self.p(rel))   # as an earlier run recorded it
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_install_then_doctor_is_ok(self):
        install("install", "--track", "rust", "--root", self.tmp)
        self.older()
        self.record()
        out = install("update", "--track", "rust", "--root", self.tmp)
        self.assertIn("overwritten " + GATE, out)
        self.assertEqual(self.item()["status"], "ok", self.item()["detail"])

    def test_crlf_older_copy_then_doctor_is_ok(self):
        install("install", "--track", "rust", "--root", self.tmp)
        self.older(crlf=True)
        self.record()
        install("update", "--track", "rust", "--root", self.tmp)
        self.assertEqual(self.item()["status"], "ok", self.item()["detail"])

    def test_locally_edited_script_still_warns(self):
        install("install", "--track", "rust", "--root", self.tmp)
        self.write(GATE, self.read(GATE) + b"# mine\n")
        self.assertEqual(self.item()["status"], "warn")
        self.assertIn(GATE, self.item()["detail"])

    def test_ts_without_packaged_program_is_ok(self):
        install("install", "--track", "ts", "--root", self.tmp)
        self.assertFalse(os.path.exists(self.p("scripts/delivery/smoke.json")))
        self.assertEqual(self.item()["status"], "ok", self.item()["detail"])

    def test_old_copy_without_record_is_not_reported_as_merged(self):
        install("install", "--track", "rust", "--root", self.tmp)
        self.older()
        os.remove(self.p(INS.STATE))
        shutil.rmtree(self.p(INS.BASE_DIR))
        for _ in range(2):   # the second run used to say "merged" and leave the old file
            out = install("update", "--track", "rust", "--root", self.tmp)
            self.assertIn("kept (project changes) " + GATE, out)
            self.assertNotIn("merged      " + GATE, out)
            self.assertTrue(os.path.exists(self.p(GATE + ".new")))
        self.assertEqual(self.item()["status"], "warn")
        self.assertIn(GATE, self.item()["detail"])
        # the owner copies the .new over the file: the warning goes
        self.write(GATE, self.read(GATE + ".new"))
        self.write(RERUN, self.read(RERUN + ".new"))
        install("update", "--track", "rust", "--root", self.tmp)
        self.assertEqual(self.item()["status"], "ok", self.item()["detail"])


if __name__ == "__main__":
    unittest.main()
