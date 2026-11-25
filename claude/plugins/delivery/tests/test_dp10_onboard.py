"""DP10: one-command onboarding in warn mode that asks the merge mode (R5.73)."""
import json
import os
import tempfile
import unittest

import _helpers  # noqa: F401  (sets the script path)

import delivery_config as C
import delivery_onboard as O


class OnboardTests(unittest.TestCase):
    def test_writes_warn_mode_config_and_ledger(self):
        root = tempfile.mkdtemp(prefix="dp10-")
        files = O.onboard(root, "manual")
        self.assertEqual(len(files), 2)
        cfg = json.load(open(os.path.join(root, ".delivery", "config.json"), encoding="utf-8"))
        self.assertEqual(cfg["enforcement"]["mode"], "warn")
        self.assertEqual(C.merge_mode(cfg), "manual")
        self.assertFalse([k for k in cfg if k.startswith("_")])
        self.assertEqual(C.validate_config(cfg), ([], []))
        led = json.load(open(os.path.join(root, ".delivery", "ledger.json"), encoding="utf-8"))
        self.assertEqual(led["trains"], [])

    def test_existing_config_is_never_touched(self):
        root = tempfile.mkdtemp(prefix="dp10-")
        os.makedirs(os.path.join(root, ".delivery"))
        p = os.path.join(root, ".delivery", "config.json")
        open(p, "w").write("{}")
        with self.assertRaises(FileExistsError):
            O.onboard(root, "auto")
        self.assertEqual(open(p).read(), "{}")

    def test_no_default_merge_mode(self):
        root = tempfile.mkdtemp(prefix="dp10-")
        self.assertEqual(O.main(["--root", root]), 2)
        self.assertFalse(os.path.exists(os.path.join(root, ".delivery")))
        with self.assertRaises(ValueError):
            O.onboard(root, "")

    def test_main_writes_with_the_flag(self):
        root = tempfile.mkdtemp(prefix="dp10-")
        self.assertEqual(O.main(["--root", root, "--merge-mode", "auto"]), 0)
        self.assertEqual(O.main(["--root", root, "--merge-mode", "auto"]), 1)


if __name__ == "__main__":
    unittest.main()
