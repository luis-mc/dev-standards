"""DS276: a merged entry that is not cleaned or smoked is not idle (DL-130)."""
import json
import unittest

from _helpers import make_root
import hook_stop as S


class MergedNotIdleTests(unittest.TestCase):
    def check(self, train):
        root = make_root()
        d = root / "docs" / "project"
        d.mkdir(parents=True)
        (d / "registry.json").write_text(json.dumps({"tasks": [{"id": "DS1", "status": "Running"}]}))
        return S.check_running_idle(str(root), {"agents": [], "trains": [train]}, {})

    def test_merged_not_cleaned_is_quiet(self):
        self.assertEqual(self.check({"state": "merged", "merged_at": "2026-11-26T10:00:00Z", "cargo": [{"task": "DS1"}]}), [])

    def test_merged_cleaned_not_smoked_is_quiet(self):
        self.assertEqual(self.check({"state": "merged", "merged_at": "x", "cleaned_at": "y", "cargo": [{"task": "DS1"}]}), [])

    def test_cleaned_and_smoked_warns_again(self):
        t = {"state": "merged", "merged_at": "x", "cleaned_at": "y", "smoke": {"state": "pass"}, "cargo": [{"task": "DS1"}]}
        self.assertEqual(len(self.check(t)), 1)
        t["state"] = "cleaned"
        self.assertEqual(len(self.check(t)), 1)


if __name__ == "__main__":
    unittest.main()
