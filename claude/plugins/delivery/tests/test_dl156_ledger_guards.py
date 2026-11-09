"""DL156: unique train ids, no taskless agent rows, CI matched by PR and head SHA, readable `show`."""
import contextlib
import io
import json
import unittest
from argparse import Namespace

from _helpers import make_root, L


def seed(root, data):
    """Write old-style rows straight to the file, as an older ledger would hold them."""
    led = L.empty_ledger()
    led.update(data)
    L.write_atomic(root, led)


class TrainIds(unittest.TestCase):
    def test_plan_takes_next_free_id(self):
        root = make_root()
        L.update(root, lambda led: L.new_train(led, "a"))
        L.update(root, lambda led: L.new_train(led, "b"))
        L.update(root, lambda led: led["trains"].pop(0))   # a count would now repeat the second id
        box = {}
        L.update(root, lambda led: box.update(t=L.new_train(led, "c")))
        ids = [t["id"] for t in L.load(root)["trains"]]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(box["t"]["id"].endswith("-03"))

    def test_duplicate_id_refused(self):
        root = make_root()
        L.update(root, lambda led: L.new_train(led, "a"))
        tid = L.load(root)["trains"][0]["id"]

        def dup(led):
            led["trains"].append({"id": tid, "branch": "x"})
        with self.assertRaises(L.LedgerError) as cm:
            L.update(root, dup)
        self.assertIn(tid, str(cm.exception))
        self.assertEqual(len(L.load(root)["trains"]), 1)

    def test_old_duplicates_still_load_and_write(self):
        root = make_root()
        seed(root, {"trains": [{"id": "T-1", "branch": "a"}, {"id": "T-1", "branch": "b"}]})
        L.update(root, lambda led: L.add_event(led, "x"))
        self.assertEqual(len(L.load(root)["trains"]), 2)


class AgentRows(unittest.TestCase):
    def test_taskless_agent_refused(self):
        root = make_root()
        with self.assertRaises(L.LedgerError) as cm:
            L.update(root, lambda led: led["agents"].append({"id": "a1", "task": None, "state": "running"}))
        self.assertIn("task", str(cm.exception))
        self.assertEqual(L.load(root)["agents"], [])

    def test_old_taskless_row_still_writes(self):
        root = make_root()
        seed(root, {"agents": [{"id": "old", "task": None, "state": "running"}]})
        L.update(root, lambda led: led["agents"].append({"id": "a2", "task": "T2", "state": "running"}))
        self.assertEqual(len(L.load(root)["agents"]), 2)


class CiMatch(unittest.TestCase):
    def two_trains(self):
        root = make_root()
        seed(root, {"trains": [
            {"id": "T-1", "branch": "a", "pr": 1, "state": "ci", "hold": None, "cargo": [],
             "ci": {"head_sha": "aaaaaaa1", "state": "queued"}},
            {"id": "T-1", "branch": "b", "pr": 2, "state": "ci", "hold": None, "cargo": [],
             "ci": {"head_sha": "bbbbbbb2", "state": "queued"}}]})
        return root

    def test_result_lands_on_the_pr_row(self):
        root = self.two_trains()
        self.assertTrue(L.record(root, "ci", train="T-1", pr=2, sha="bbbbbbb2", state="success"))
        t = L.load(root)["trains"]
        self.assertEqual(t[1]["ci"]["state"], "success")
        self.assertEqual(t[0]["ci"]["state"], "queued")

    def test_id_alone_never_matches_a_train_with_a_pr(self):
        root = self.two_trains()
        L.record(root, "ci", train="T-1", sha="ccccccc3", state="success")
        t = L.load(root)["trains"]
        self.assertEqual([x["ci"]["state"] for x in t], ["queued", "queued"])

    def test_sha_alone_matches(self):
        root = self.two_trains()
        L.record(root, "ci", sha="aaaaaaa1", state="failure")
        self.assertEqual(L.load(root)["trains"][0]["ci"]["state"], "failure")


class Show(unittest.TestCase):
    def test_show_prints_task_id_branch(self):
        root = make_root()
        seed(root, {"agents": [{"task": "T1", "id": "a1", "branch": "T1-x", "state": "running"},
                               {"task": None, "id": "a2", "state": "running"}]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            L._cmd_show(root, Namespace(json=False))
        text = out.getvalue()
        self.assertIn("agent T1 a1 T1-x state=running", text)
        self.assertIn("agent - a2 - state=running", text)
        self.assertNotIn("None", text)


if __name__ == "__main__":
    unittest.main()
