"""DL323: several pool agents for one repository share the routing label."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "templates" / "runner-pool" / "pool_agents.py"
spec = importlib.util.spec_from_file_location("pool_agents_dl323", SRC)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class R:
    returncode, stdout, stderr = 0, "", ""


class Pool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.join(self.tmp.name, "agents")
        os.makedirs(self.base)
        self.file = os.path.join(self.tmp.name, "agents.json")
        self.calls = []
        A.create_db = lambda *a, **k: None
        A.kvm_usable = lambda *a, **k: False

    def run_(self, argv, **kw):
        self.calls.append(argv)
        return R()

    def add(self, slug, repo="o/r", **kw):
        return A.add_agent(slug, repo, "tok", "main", True, self.file, self.base, run=self.run_, **kw)

    def agents(self):
        return json.load(open(self.file))["agents"]

    def labels_of(self, slug):
        return [a for a in self.agents() if a["slug"] == slug][0]["labels"]

    def test_second_agent_gets_route_slug(self):
        self.add("alpha")
        msg = self.add("other")
        self.assertIn("alpha-2", msg)
        self.assertEqual([a["slug"] for a in self.agents()], ["alpha", "alpha-2"])
        self.assertIn("repo-alpha", self.labels_of("alpha-2"))
        self.assertNotIn("repo-alpha-2", self.labels_of("alpha-2"))
        self.assertEqual(self.agents()[1]["route"], "alpha")
        self.assertEqual(self.agents()[1]["user"], "r-alpha-2")
        self.assertTrue(os.path.isdir(os.path.join(self.base, "alpha-2")))

    def test_third_agent_counts_on(self):
        self.add("alpha")
        self.add("x")
        self.add("y")
        self.assertEqual([a["slug"] for a in self.agents()], ["alpha", "alpha-2", "alpha-3"])

    def test_explicit_route(self):
        self.add("beta", route="shared")
        self.assertIn("repo-shared", self.labels_of("beta"))
        self.assertEqual(self.agents()[0]["route"], "shared")

    def test_old_entries_unchanged(self):
        json.dump({"agents": [{"slug": "old", "user": "r-old", "repo": "o/r", "private": True,
                               "labels": ["repo-old"]}]}, open(self.file, "w"))
        self.assertEqual(A.route_of(self.agents()[0]), "old")
        self.add("n")
        self.assertEqual(self.agents()[0], {"slug": "old", "user": "r-old", "repo": "o/r", "private": True,
                                            "labels": ["repo-old"]})
        self.assertIn("repo-old", self.labels_of("old-2"))

    def test_first_agent_has_no_route_key(self):
        self.add("solo")
        self.assertNotIn("route", self.agents()[0])
        self.assertIn("repo-solo", self.labels_of("solo"))

    def test_other_repo_not_shared(self):
        self.add("alpha")
        self.add("gamma", repo="o/other")
        self.assertEqual(self.agents()[1]["slug"], "gamma")
        self.assertIn("repo-gamma", self.labels_of("gamma"))

    def test_rerun_of_existing_slug_stays(self):
        self.add("alpha")
        self.add("x")
        self.assertIn("already added", self.add("alpha-2"))
        self.assertEqual(len(self.agents()), 2)

    def test_bad_route(self):
        with self.assertRaises(A.PoolError):
            self.add("a", route="Bad Route")

    def test_remove_keeps_other(self):
        self.add("alpha")
        self.add("x")
        A.remove_agent("alpha", "tok", self.file, self.base, run=self.run_)
        left = self.agents()
        self.assertEqual([a["slug"] for a in left], ["alpha-2"])
        self.assertIn("repo-alpha", left[0]["labels"])
        self.assertTrue(os.path.isdir(os.path.join(self.base, "alpha-2")))


if __name__ == "__main__":
    unittest.main()
