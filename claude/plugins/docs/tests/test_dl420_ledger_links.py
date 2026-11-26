"""DL420: Full Progress reads a release's PR and its waits-on from the delivery ledger (R5.59)."""
import json
import unittest

from _helpers import *  # noqa
import render_artifacts as R


def rel(tid, n, **kw):
    t = {"id": tid, "item": tid, "detail": "d", "expected": "", "status": "Running", "release": n}
    t.update(kw)
    return t


def train(tid, pr=None, **kw):
    t = {"id": "T" + tid, "release_no": None, "branch": tid + "-integration", "pr": pr, "state": "ci"}
    t.update(kw)
    return t


def setup(trains, config=None, git_repo=False):
    d = make_repo({"docs/project/registry.json": "{}"}) if git_repo else make_repo({"docs/project/x": "x"})
    w(d, ".delivery/ledger.json", json.dumps({"schema": 1, "trains": trains}))
    if config is not None:
        w(d, ".delivery/config.json", json.dumps(config))
    return d, str(d / "docs" / "project")


def tasks_of(tasks, record):
    return {t["id"]: t for t in R._tasks({"tasks": tasks}, record)}


class LedgerLinks(unittest.TestCase):
    def test_pr_comes_from_the_ledger_by_branch(self):
        d, rec = setup([train("DL1", pr=11), train("DL2", pr=12)])
        got = tasks_of([rel("DL1", 1), rel("DL2", 2)], rec)
        self.assertEqual((got["DL1"]["pr"], got["DL2"]["pr"]), (11, 12))
        self.assertTrue(R.tree_mode(list(got.values())))

    def test_explicit_pr_and_waits_win(self):
        d, rec = setup([train("DL1", pr=11), train("DL2", pr=12)], {"deploy": {"serial": True}})
        got = tasks_of([rel("DL1", 1, state="x"), rel("DL2", 2, pr=99, release_waits_on=["RELEASE-9"])], rec)
        self.assertEqual(got["DL2"]["pr"], 99)
        self.assertEqual(got["DL2"]["release_waits_on"], ["RELEASE-9"])

    def test_no_ledger_changes_nothing(self):
        d = make_repo({"docs/project/x": "x"})
        got = tasks_of([rel("DL1", 1)], str(d / "docs" / "project"))
        self.assertNotIn("pr", got["DL1"])
        self.assertFalse(R.tree_mode(list(got.values())))

    def test_serial_waits_on_earlier_merged_train(self):
        trains = [train("DL1", pr=11, state="merged"), train("DL2", pr=12)]
        d, rec = setup(trains, {"deploy": {"serial": True}})
        got = tasks_of([rel("DL1", 1), rel("DL2", 2)], rec)
        self.assertEqual(got["DL2"]["release_waits_on"], ["DL1"])
        self.assertNotIn("release_waits_on", got["DL1"])

    def test_not_serial_no_wait(self):
        trains = [train("DL1", pr=11, state="merged"), train("DL2", pr=12)]
        d, rec = setup(trains, {})
        got = tasks_of([rel("DL1", 1), rel("DL2", 2)], rec)
        self.assertNotIn("release_waits_on", got["DL2"])

    def test_live_release_is_not_waited_on(self):
        trains = [train("DL1", pr=11, state="merged"), train("DL2", pr=12)]
        d, rec = setup(trains, {"deploy": {"serial": True}})
        got = tasks_of([rel("DL1", 1, status="Live"), rel("DL2", 2)], rec)
        self.assertNotIn("release_waits_on", got["DL2"])

    def test_ancestry_wait(self):
        d = make_repo({"a.txt": "a"})
        git(d, "checkout", "-q", "-b", "DL1-integration")
        w(d, "one.txt", "1")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "one")
        git(d, "checkout", "-q", "-b", "DL2-integration")
        w(d, "two.txt", "2")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "two")
        git(d, "checkout", "-q", "main")
        w(d, ".delivery/ledger.json", json.dumps({"trains": [train("DL1", pr=11), train("DL2", pr=12)]}))
        got = tasks_of([rel("DL1", 1), rel("DL2", 2)], str(d / "docs" / "project"))
        self.assertEqual(got["DL2"]["release_waits_on"], ["DL1"])

    def test_disjoint_branches_do_not_wait(self):
        d = make_repo({"a.txt": "a"})
        for name in ("DL1", "DL2"):
            git(d, "checkout", "-q", "-b", name + "-integration", "main")
            w(d, name + ".txt", name)
            git(d, "add", "-A")
            git(d, "commit", "-q", "-m", name)
        git(d, "checkout", "-q", "main")
        w(d, ".delivery/ledger.json", json.dumps({"trains": [train("DL1"), train("DL2")]}))
        got = tasks_of([rel("DL1", 1), rel("DL2", 2)], str(d / "docs" / "project"))
        self.assertNotIn("release_waits_on", got["DL2"])

    def test_unreadable_ledger_is_ignored(self):
        d = make_repo({"docs/project/x": "x"})
        w(d, ".delivery/ledger.json", "{not json")
        got = tasks_of([rel("DL1", 1)], str(d / "docs" / "project"))
        self.assertNotIn("pr", got["DL1"])


if __name__ == "__main__":
    unittest.main()
