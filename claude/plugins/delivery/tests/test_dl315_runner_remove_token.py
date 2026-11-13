"""DL315: the Windows runner setup removes a runner already in the folder with a remove token, checks the result, and
does it before the folder is locked to the new account."""
import unittest

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_runner_pool as P
from test_dl310_windows_runner import REPO, Probe, found, plan


class RemoveToken(unittest.TestCase):
    def setUp(self):
        self.step = next(s for s in plan(found(), Probe())["steps"] if s["id"] == "winsvc:" + REPO)
        self.text = P.windows_runner_script(self.step)

    def test_remove_uses_a_remove_token(self):
        self.assertIn("repos/%s/actions/runners/remove-token" % REPO, self.text)
        self.assertIn("config.cmd remove --token $rt", self.text)
        self.assertNotIn("config.cmd remove --token $token", self.text)

    def test_remove_failure_stops_the_script(self):
        self.assertIn("$code = $LASTEXITCODE", self.text)
        self.assertIn("if ($code -ne 0) { throw", self.text)
        self.assertNotIn("remove --token $rt | Out-Null", self.text)

    def test_remove_comes_before_the_folder_lock(self):
        remove = self.text.index("config.cmd remove")
        lock = self.text.index("icacls $folder /inheritance:r")
        self.assertLess(remove, lock)

    def test_no_remove_without_registration(self):
        lines = P.ps_files("ci-x", "C:/actions-runners/x", "C:/ci-tools", "python", repo=REPO, unregister=False)
        self.assertFalse(any("config.cmd remove" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
