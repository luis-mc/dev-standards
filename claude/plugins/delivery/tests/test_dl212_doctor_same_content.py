"""DL212: a file identical to the template is ok, whatever the install record says."""
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

REL = "scripts/delivery/join.py"


def quiet_install(*argv):
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        return INS.main(list(argv))


class SameContent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        quiet_install("install", "--track", "rust", "--root", self.tmp)
        self.sp = os.path.join(self.tmp, INS.STATE.replace("/", os.sep))
        with open(self.sp, encoding="utf-8") as f:
            self.data = json.load(f)

    def save(self):
        with open(self.sp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)

    def status(self):
        return [i for i in DOC.scripts_items(self.tmp) if i["id"] == "ci.scripts-current"][0]["status"]

    def test_wrong_hash_is_ok_and_update_rewrites_it(self):
        self.data["files"][REL] = "0" * 64
        self.save()
        self.assertEqual(self.status(), "ok")
        quiet_install("update", "--root", self.tmp)
        with open(self.sp, encoding="utf-8") as f:
            self.assertNotEqual(json.load(f)["files"][REL], "0" * 64)

    def test_stale_new_file_beside_identical_file_is_ok(self):
        with open(os.path.join(self.tmp, REL + ".new"), "w") as f:
            f.write("old\n")
        self.assertEqual(self.status(), "ok")

    def test_edited_file_still_warns(self):
        with open(os.path.join(self.tmp, REL), "a") as f:
            f.write("# mine\n")
        self.assertEqual(self.status(), "warn")


if __name__ == "__main__":
    unittest.main()
