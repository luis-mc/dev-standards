"""DL163: two releases on one day never share a train id (plan, join-created rows, link); old duplicates load and
show warns. Temp ledger, no network."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _helpers import make_root, L  # noqa: E402


def ids(root):
    return [t["id"] for t in L.load(root)["trains"]]


def run(root, *argv, runner=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = L.main(["--root", str(root)] + list(argv))
    return rc, out.getvalue()


class UniqueIds(unittest.TestCase):
    def test_plan_twice(self):
        root = make_root()
        run(root, "plan", "--branch", "r1-integration")
        run(root, "plan", "--branch", "r2-integration")
        got = ids(root)
        self.assertEqual(len(set(got)), 2, got)

    def test_join_created_rows(self):
        root = make_root()
        for br, sha in (("r1-integration", "a" * 7), ("r2-integration", "b" * 7)):
            self.assertTrue(L.record(root, "ci", branch=br, sha=sha, state="queued", create=True, by="join.py"))
        got = ids(root)
        self.assertEqual(len(set(got)), 2, got)

    def test_join_train_state_creates_row(self):
        root = make_root()
        run(root, "plan", "--branch", "r1-integration")
        L.record(root, "train_state", branch="r2-integration", state="pushed", by="join.py", create=True)
        L.record(root, "cargo", branch="r2-integration", task="X1", by="join.py", fields={"gate": "ci"})
        rows = L.load(root)["trains"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({t["id"] for t in rows}), 2)

    def test_link_new_branch_makes_new_row(self):
        root = make_root()
        run(root, "plan", "--branch", "r1-integration")
        L.update(root, lambda led: led["trains"][0].update(pr=10))
        args = ["link", "--pr", "11", "--sha", "abc1234", "--branch", "r2-integration"]
        rc, _ = run(root, *args)
        self.assertEqual(rc, 0)
        rows = L.load(root)["trains"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({t["id"] for t in rows}), 2)
        self.assertEqual(rows[0]["pr"], 10)
        self.assertEqual(rows[1]["pr"], 11)
        self.assertEqual(rows[1]["branch"], "r2-integration")

    def test_write_refuses_more_copies_of_old_duplicate(self):
        root = make_root()
        (root / ".delivery" / "ledger.json").write_text(json.dumps({"trains": [
            {"id": "T-2026-01-01-01", "branch": "a", "state": "merged"},
            {"id": "T-2026-01-01-01", "branch": "b", "state": "merged"}]}))
        with self.assertRaises(L.LedgerError):
            L.update(root, lambda led: led["trains"].append({"id": "T-2026-01-01-01", "branch": "c", "state": "planned"}))


class OldDuplicates(unittest.TestCase):
    def test_loads_and_show_warns(self):
        root = make_root()
        (root / ".delivery" / "ledger.json").write_text(json.dumps({"trains": [
            {"id": "T-2026-01-01-04", "branch": "a", "state": "merged"},
            {"id": "T-2026-01-01-04", "branch": "b", "state": "planned"}]}))
        self.assertEqual(len(L.load(root)["trains"]), 2)
        rc, out = run(root, "show")
        self.assertEqual(rc, 0)
        self.assertIn("WARNING", out)
        self.assertIn("T-2026-01-01-04", out)
        self.assertIn("plan", out)


if __name__ == "__main__":
    unittest.main()
