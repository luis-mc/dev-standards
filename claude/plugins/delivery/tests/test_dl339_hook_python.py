"""DL339 (R5.46, R5.47): the hook Python is never a per-user path. Mocked paths and probe; runs on Linux CI."""
import os
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)

import delivery_doctor as D  # noqa: E402
import delivery_runner_pool as P  # noqa: E402

USER_PY = "C:\\Users\\<user>\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"
ALL_PY = "C:/Program Files/Python312/python.exe"


class FakeProbe:
    def __init__(self, py_list="", existing=()):
        self.py_list, self.existing = py_list, set(existing)

    def sh(self, argv, input=None, timeout=60):
        return (0, self.py_list) if argv[:2] == ["py", "-0p"] else None

    def exists(self, path):
        return path in self.existing


class ChooseTest(unittest.TestCase):
    def test_per_user_rejected_all_users_chosen(self):
        out = " -V:3.12 *  %s\n -V:3.11    C:\\Program Files\\Python311\\python.exe\n" % USER_PY
        pr = FakeProbe(out, {"C:\\Program Files\\Python311\\python.exe"})
        py, err = P.choose_hook_python(None, USER_PY, pr)
        self.assertIsNone(err)
        self.assertEqual(py.replace("\\", "/"), "C:/Program Files/Python311/python.exe")

    def test_explicit_host_python_wins(self):
        py, err = P.choose_hook_python("D:/Tools/Py/python.exe", USER_PY, FakeProbe())
        self.assertIsNone(err)
        self.assertIn("Tools", py)

    def test_non_profile_exe_is_kept(self):
        py, err = P.choose_hook_python(None, ALL_PY, FakeProbe())
        self.assertIsNone(err)
        self.assertIn("Program Files", py)

    def test_no_candidate_gives_message(self):
        py, err = P.choose_hook_python(None, USER_PY, FakeProbe("", ()))
        self.assertIsNone(py)
        self.assertIn("Install for all users", err)
        self.assertIn("machine config", err)

    def test_profile_paths(self):
        for p in (USER_PY, "c:/users/x/python.exe", "D:/z/AppData/Local/Python/python.exe"):
            self.assertTrue(P.is_user_profile_path(p), p)
        self.assertFalse(P.is_user_profile_path(ALL_PY))


class DoctorTest(unittest.TestCase):
    def _items(self, py, exists):
        with tempfile.TemporaryDirectory() as d:
            for n in ("runner_load_gate.ps1", "runner_job_done.ps1"):
                with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                    f.write(P.hook_wrapper(py, n.replace(".ps1", ".py")))
            return D.hook_python_items(d, exists=lambda p: exists)

    def test_per_user_line_fails(self):
        items = self._items(USER_PY, True)
        self.assertEqual({i["status"] for i in items}, {"fail"})
        self.assertIn("Install for all users", items[0]["detail"])

    def test_program_files_passes(self):
        self.assertEqual({i["status"] for i in self._items(ALL_PY, True)}, {"ok"})

    def test_missing_python_fails(self):
        self.assertEqual({i["status"] for i in self._items(ALL_PY, False)}, {"fail"})


if __name__ == "__main__":
    unittest.main()
