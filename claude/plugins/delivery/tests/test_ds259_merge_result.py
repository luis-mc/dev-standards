"""DS259 (DL-119): test the merge result before the watcher merges. Fake gh and git; no network."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import test_watch as T
from _helpers import L
import delivery_config as C

TREE = "c" * 40


def routes(behind, own_tree=TREE, merge_tree=TREE, compare_rc=0):
    r = T.routes_for_green()
    r[("gh", "api", "repos/{owner}/{repo}/compare/main..." + T.SHA)] = (compare_rc, json.dumps({"behind_by": behind}))
    r[("git", "merge-tree")] = (0, merge_tree + "\n")
    r[("git", "rev-parse", T.SHA + "^{tree}")] = (0, own_tree + "\n")
    r[("gh", "pr", "update-branch")] = (0, "")
    return r


def go(cfg, r):
    root = T.make_root(cfg)
    T.seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
    sh = T.FakeShell(r)
    lines = []
    w = T.W.Watcher(root, sh=sh, now=lambda: T.NOW, out=lines.append, ci_runs=False)
    w.run_once()
    return root, sh, lines


def merges(sh):
    return [c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]]


def updates(sh):
    return [c for c in sh.calls if c[:3] == ["gh", "pr", "update-branch"]]


class MergeResultTests(unittest.TestCase):
    def test_not_behind_merges_with_no_extra_call(self):
        root, sh, lines = go({}, routes(0))
        self.assertEqual(len(merges(sh)), 1)
        self.assertFalse(any(c[:2] == ["git", "merge-tree"] for c in sh.calls))
        self.assertEqual(lines, [])

    def test_behind_default_warns_once_and_merges(self):
        root, sh, lines = go({}, routes(3, own_tree="d" * 40))
        self.assertEqual(len(merges(sh)), 1)
        self.assertEqual(updates(sh), [])
        warn = [x for x in lines if "behind main" in x]
        self.assertEqual(len(warn), 1)
        self.assertIn("3 commit(s) behind main", warn[0])
        kinds = [e["kind"] for e in L.load(root)["events"]]
        self.assertIn("merge.untested_result", kinds)

    def test_merge_tree_equal_to_head_tree_merges_silently(self):
        root, sh, lines = go({"watcher": {"merge_result": "update"}}, routes(2))
        self.assertEqual(len(merges(sh)), 1)
        self.assertEqual(updates(sh), [])
        self.assertEqual(lines, [])

    def test_update_mode_updates_branch_and_does_not_merge(self):
        root, sh, lines = go({"watcher": {"merge_result": "update"}}, routes(2, own_tree="d" * 40))
        self.assertEqual(merges(sh), [])
        self.assertEqual(updates(sh), [["gh", "pr", "update-branch", "10", "--expected-head-sha", T.SHA]])
        self.assertIn("merge.branch_updated", [e["kind"] for e in L.load(root)["events"]])
        self.assertEqual(L.load(root)["trains"][0]["state"], "green")

    def test_update_mode_failure_does_not_merge(self):
        r = routes(2, own_tree="d" * 40)
        r[("gh", "pr", "update-branch")] = (1, "")
        root, sh, lines = go({"watcher": {"merge_result": "update"}}, r)
        self.assertEqual(merges(sh), [])
        self.assertIn("merge.update_failed", [e["kind"] for e in L.load(root)["events"]])

    def test_unreadable_compare_merges_as_before(self):
        for mode in ("warn", "update"):
            root, sh, lines = go({"watcher": {"merge_result": mode}}, routes(5, compare_rc=1))
            self.assertEqual(len(merges(sh)), 1, mode)
            self.assertEqual(updates(sh), [], mode)

    def test_conflicting_merge_tree_still_counts_as_untested(self):
        r = routes(1)
        r[("git", "merge-tree")] = (1, "")
        root, sh, lines = go({}, r)
        self.assertEqual(len(merges(sh)), 1)
        self.assertTrue(any("behind main" in x for x in lines))

    def test_base_follows_config(self):
        r = routes(1, own_tree="d" * 40)
        r[("gh", "api", "repos/{owner}/{repo}/compare/trunk..." + T.SHA)] = (0, json.dumps({"behind_by": 4}))
        root, sh, lines = go({"base": "trunk"}, r)
        self.assertTrue(any("4 commit(s) behind trunk" in x for x in lines))


class ConfigTests(unittest.TestCase):
    def test_merge_result_accessor(self):
        self.assertEqual(C.merge_result({}), "warn")
        self.assertEqual(C.merge_result({"watcher": {"merge_result": "update"}}), "update")
        self.assertEqual(C.merge_result({"watcher": {"merge_result": "x"}}), "warn")

    def test_schema_lists_the_key(self):
        schema = json.loads(Path(C.SCHEMA_PATH).read_text(encoding="utf-8"))
        prop = schema["properties"]["watcher"]["properties"]["merge_result"]
        self.assertEqual(prop["enum"], ["warn", "update"])
        self.assertEqual(prop["default"], "warn")


if __name__ == "__main__":
    unittest.main()
