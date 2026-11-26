"""DS277: link sets the pull request on the releases of its cargo tasks (DL-131)."""
import json
import unittest

from _helpers import make_root
import delivery_ledger as L


class Res:
    returncode = 0


class LinkSetsPrTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        d = self.root / "docs" / "project"
        d.mkdir(parents=True)
        self.reg = {"tasks": [
            {"id": "R1", "release": 1, "status": "Running"},
            {"id": "R2", "release": 2, "status": "Built", "pr": 9},
            {"id": "R3", "release": 3, "status": "Built"},
            {"id": "A", "status": "Running", "rides": "R1"},
            {"id": "B", "status": "Running", "rides": "R2"},
            {"id": "C", "status": "Live", "rides": "R3"},
        ]}
        (d / "registry.json").write_text(json.dumps(self.reg))
        self.calls = []

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        return Res()

    def test_sets_pr_on_releases_without_one(self):
        got = L.set_release_prs(self.root, ["A", "B", "C"], 7, runner=self.runner)
        self.assertEqual(got, ["R1"])
        self.assertEqual(self.calls[0][-5:], ["set-task-status", "R1", "Running", "--pr", "7"])
        self.assertEqual(len(self.calls), 1)

    def test_no_record_changes_nothing(self):
        (self.root / "docs" / "project" / "registry.json").unlink()
        self.assertEqual(L.set_release_prs(self.root, ["A"], 7, runner=self.runner), [])
        self.assertEqual(self.calls, [])

    def test_runner_error_never_raises(self):
        def boom(cmd, **kw):
            raise OSError("no")
        self.assertEqual(L.set_release_prs(self.root, ["A"], 7, runner=boom), [])


if __name__ == "__main__":
    unittest.main()
